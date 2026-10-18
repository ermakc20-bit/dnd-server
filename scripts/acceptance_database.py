"""Replay migrations/pgTAP in a new owned database; never reset an existing database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]

SCAFFOLD = """
create schema extensions; create schema auth; create schema storage;
create table auth.users(id uuid primary key, email text,
  raw_user_meta_data jsonb not null default '{}'::jsonb);
create table storage.buckets(id text primary key, name text not null, public boolean,
  file_size_limit bigint, allowed_mime_types text[]);
"""


def statements(sql: str) -> list[str]:
    """Split SQL scripts without breaking quoted function/diagnostic bodies."""
    result: list[str] = []
    start = index = 0
    quote = ""
    while index < len(sql):
        if quote:
            if sql.startswith(quote, index):
                if quote in {"'", '"'} and sql.startswith(quote * 2, index):
                    index += 2
                    continue
                index += len(quote)
                quote = ""
                continue
        elif sql.startswith("--", index):
            end = sql.find("\n", index)
            index = len(sql) if end == -1 else end
            continue
        elif sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end == -1:
                raise ValueError("unterminated SQL comment")
            index = end + 2
            continue
        elif sql[index] in {"'", '"'}:
            quote = sql[index]
        elif sql[index] == "$":
            match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", sql[index:])
            if match:
                quote = match[0]
                index += len(quote)
                continue
        elif sql[index] == ";":
            result.append(sql[start : index + 1])
            start = index + 1
        index += 1
    if quote:
        raise ValueError("unterminated SQL quote")
    if sql[start:].strip():
        result.append(sql[start:])
    return result


def admin_destination(url: str) -> str:
    destination = urlparse(url)
    if (
        destination.scheme not in {"postgres", "postgresql"}
        or destination.hostname not in {"127.0.0.1", "localhost"}
        or destination.username != "postgres"
        or destination.query
        or destination.fragment
    ):
        raise ValueError("only explicit localhost synthetic PostgreSQL is allowed")
    if destination.path not in {"/postgres", "/vtt_ticket01"}:
        raise ValueError("unsupported admin source")
    return destination._replace(path="/postgres").geturl()


async def replay(url: str, root: Path, *, prepare: bool = False) -> dict[str, object]:
    admin = await asyncpg.connect(admin_destination(url), timeout=10)
    name = "vtt_ticket01" if prepare else "vtt_acceptance_" + uuid4().hex
    created = False
    database = None
    cleanup = False
    completed = False
    try:
        for role in ("anon", "authenticated", "service_role"):
            if not await admin.fetchval(
                "select exists(select 1 from pg_roles where rolname=$1)", role
            ):
                raise ValueError("local Supabase-compatible roles required")
        if await admin.fetchval("select exists(select 1 from pg_database where datname=$1)", name):
            raise ValueError("destination already exists; it will not be reset")
        await admin.execute(f'create database "{name}"')
        created = True
        database = await asyncpg.connect(
            urlparse(admin_destination(url))._replace(path="/" + name).geturl(), timeout=10
        )
        await database.execute(SCAFFOLD)
        migrations = sorted((root / "supabase" / "migrations").glob("*.sql"))
        suites = sorted((root / "supabase" / "tests").glob("*.sql"))
        if not migrations or not suites:
            raise ValueError("migration/test files missing")
        for migration in migrations:
            async with database.transaction():
                await database.execute(migration.read_text())
        await database.execute("create extension if not exists pgtap with schema extensions")
        await database.execute("set search_path=app,extensions,public")
        passed = 0
        for suite in suites:
            planned = observed = 0
            for statement in statements(suite.read_text()):
                rows = await database.fetch(statement)
                for row in rows:
                    value = str(row[0])
                    if re.search(r"#\s*(?:SKIP|TODO)\b", value, re.IGNORECASE):
                        raise ValueError("pgTAP assertion was not an unconditional executed pass")
                    if re.match(r"not ok\b", value) or "Looks like you" in value:
                        raise ValueError("pgTAP assertion failed")
                    if re.match(r"ok\b", value):
                        observed += 1
                    if re.fullmatch(r"1\.\.\d+", value):
                        planned = int(value[3:])
            if not planned or observed != planned:
                raise ValueError("incomplete pgTAP suite")
            passed += observed
        result: dict[str, object] = {
            "status": "passed",
            "migrations": len(migrations),
            "suites": len(suites),
            "pgtap_passed": passed,
            "scope": "synthetic Supabase-compatible SQL, not hosted",
        }
        completed = True
    finally:
        if database:
            await database.close()
        if created and (not prepare or not completed):
            await admin.execute(f'drop database "{name}"')
            cleanup = not await admin.fetchval(
                "select exists(select 1 from pg_database where datname=$1)", name
            )
        await admin.close()
    if not cleanup and not prepare:
        raise ValueError("owned database cleanup incomplete")
    result["owned_database_remaining"] = 1 if prepare else 0
    result["integration_database_created"] = prepare
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", default=os.getenv("VTT_TEST_DATABASE_URL", ""))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--prepare-integration",
        action="store_true",
        help="Create vtt_ticket01 only if absent; never reset it",
    )
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                asyncio.run(replay(args.admin_url, args.root, prepare=args.prepare_integration))
            )
        )
    except (OSError, ValueError, asyncpg.PostgresError) as error:
        print(json.dumps({"status": "database_error", "reason": type(error).__name__}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
