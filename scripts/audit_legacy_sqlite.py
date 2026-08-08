from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

EXPECTED_TABLES = (
    "action_logs",
    "characters",
    "custom_skills",
    "dice_history",
    "game_rooms",
    "game_tables",
    "game_tokens",
    "player_games",
    "room_players",
    "settings",
    "users",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)

    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        integrity = str(connection.execute("pragma integrity_check").fetchone()[0])
        foreign_key_violations = len(connection.execute("pragma foreign_key_check").fetchall())
        present_tables = {
            str(row[0])
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }
        counts = {
            # Table names come only from the fixed EXPECTED_TABLES allowlist above.
            table: int(
                connection.execute(f'select count(*) from "{table}"').fetchone()[0]  # noqa: S608
            )
            for table in EXPECTED_TABLES
            if table in present_tables
        }

    return {
        "path": str(path.resolve()),
        "byte_size": path.stat().st_size,
        "sha256": sha256(path),
        "integrity": integrity,
        "foreign_key_violations": foreign_key_violations,
        "missing_expected_tables": sorted(set(EXPECTED_TABLES) - present_tables),
        "row_counts": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only inventory for the legacy DnD VTT SQLite database."
    )
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.database), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
