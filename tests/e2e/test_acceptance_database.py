from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RUNNER = Path(__file__).parents[2] / "scripts" / "acceptance_database.py"


def test_database_runner_rejects_nonlocal_admin_before_connection():
    result = subprocess.run(  # noqa: S603 - fixed local acceptance CLI
        [
            sys.executable,
            str(RUNNER),
            "--admin-url",
            "postgresql://postgres@example.invalid/postgres",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "database_error" in result.stdout


def test_database_runner_never_accepts_existing_database_name():
    result = subprocess.run(  # noqa: S603 - fixed local acceptance CLI
        [sys.executable, str(RUNNER), "--name", "vtt_ticket01"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


def test_native_runner_preserves_unowned_existing_output(tmp_path):
    import os

    evidence = tmp_path / "results.json"
    evidence.write_text("existing user evidence")
    env = dict(
        os.environ,
        VTT_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:1/vtt_ticket01",
        VTT_TEST_REDIS_URL="redis://127.0.0.1:1/15",
        VTT_E2E_OUTPUT=str(tmp_path),
    )
    runner = RUNNER.parents[1] / "tests" / "e2e" / "run.py"
    result = subprocess.run(  # noqa: S603 - fixed local CLI with inaccessible synthetic services
        [sys.executable, str(runner)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 2
    assert evidence.exists() and evidence.read_text() == "existing user evidence"


def replay_cli(tmp_path, tap_value):
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "asyncpg.py").write_text(
        """from contextlib import asynccontextmanager
created = False
class PostgresError(Exception): pass
class Connection:
    async def execute(self, sql):
        global created
        if sql.startswith("create database"): created = True
        if sql.startswith("drop database"): created = False
    async def fetchval(self, sql, argument):
        return True if "pg_roles" in sql else created
    async def fetch(self, sql):
        if "plan(1)" in sql: return [("1..1",)]
        if "assertion()" in sql: return [("""
        + repr(tap_value)
        + """,)]
        return []
    async def close(self): pass
    @asynccontextmanager
    async def transaction(self): yield
async def connect(*args, **kwargs): return Connection()
"""
    )
    root = tmp_path / "repo"
    (root / "supabase" / "migrations").mkdir(parents=True)
    (root / "supabase" / "tests").mkdir()
    (root / "supabase" / "migrations" / "001.sql").write_text("select 1;")
    (root / "supabase" / "tests" / "one.sql").write_text("select plan(1);select assertion();")
    import os

    env = dict(os.environ, PYTHONPATH=str(fake))
    return subprocess.run(  # noqa: S603 - public CLI with synthetic PostgreSQL protocol adapter
        [
            sys.executable,
            str(RUNNER),
            "--root",
            str(root),
            "--admin-url",
            "postgresql://postgres@127.0.0.1/postgres",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_database_replay_rejects_skipped_assertion(tmp_path):
    result = replay_cli(tmp_path, "ok 1 # SKIP assertion not run")
    assert result.returncode == 2
    assert '"status": "passed"' not in result.stdout


def test_database_replay_rejects_todo_assertion(tmp_path):
    result = replay_cli(tmp_path, "ok 1 - expected result # TODO pending implementation")
    assert result.returncode == 2
    assert '"status": "passed"' not in result.stdout


def test_database_replay_keeps_executed_assertion_control(tmp_path):
    result = replay_cli(tmp_path, "ok 1 - executed known result")
    assert result.returncode == 0
    assert '"pgtap_passed": 1' in result.stdout
    assert '"owned_database_remaining": 0' in result.stdout


def native_cli(output):
    import os

    env = dict(
        os.environ,
        VTT_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:1/vtt_ticket01",
        VTT_TEST_REDIS_URL="redis://127.0.0.1:1/15",
        VTT_E2E_OUTPUT=str(output),
    )
    return subprocess.run(  # noqa: S603 - public local CLI with inaccessible synthetic services
        [sys.executable, str(RUNNER.parents[1] / "tests" / "e2e" / "run.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def test_native_runner_preserves_external_log_symlink_target(tmp_path):
    output = tmp_path / "owned"
    output.mkdir()
    (output / ".dnd-acceptance-owned").write_text("DND native acceptance v1\n")
    sentinel = tmp_path / "external.txt"
    sentinel.write_text("external file must remain unchanged")
    (output / "api.log").symlink_to(sentinel)
    result = native_cli(output)
    assert result.returncode == 2
    assert sentinel.read_text() == "external file must remain unchanged"
    assert (output / "api.log").is_symlink()


def test_native_runner_preserves_symlink_ancestor_target(tmp_path):
    target = tmp_path / "external"
    output = target / "owned"
    output.mkdir(parents=True)
    (output / ".dnd-acceptance-owned").write_text("DND native acceptance v1\n")
    sentinel = output / "api.log"
    sentinel.write_text("external ancestor-route file")
    route = tmp_path / "linked-parent"
    route.symlink_to(target, target_is_directory=True)
    result = native_cli(route / "owned")
    assert result.returncode == 2
    assert sentinel.read_text() == "external ancestor-route file"


def test_native_runner_preserves_external_marker_symlink_target(tmp_path):
    output = tmp_path / "owned"
    output.mkdir()
    sentinel = tmp_path / "external-marker.txt"
    sentinel.write_text("external ownership-marker file")
    (output / ".dnd-acceptance-owned").symlink_to(sentinel)
    result = native_cli(output)
    assert result.returncode == 2
    assert sentinel.read_text() == "external ownership-marker file"
