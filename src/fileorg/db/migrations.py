from __future__ import annotations

import sqlite3

from fileorg.db.models import (
    CATEGORIES_TABLE,
    CLUES_INDEX,
    CLUES_TABLE,
    ENCRYPTED_VOLUMES_TABLE,
    FILE_CATEGORIES_TABLE,
    FILES_TABLE,
    PLUGIN_COVERAGE_TABLE,
    SCAN_RUNS_TABLE,
    SCHEMA_VERSION_TABLE,
)

_MIGRATIONS: dict[int, list[str]] = {
    1: [
        SCAN_RUNS_TABLE,
        FILES_TABLE,
        CLUES_TABLE,
        CLUES_INDEX,
        CATEGORIES_TABLE,
        FILE_CATEGORIES_TABLE,
        ENCRYPTED_VOLUMES_TABLE,
        PLUGIN_COVERAGE_TABLE,
    ],
}


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(SCHEMA_VERSION_TABLE)
    conn.commit()

    row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
    current = row[0] if row[0] is not None else 0

    for version in sorted(v for v in _MIGRATIONS if v > current):
        for statement in _MIGRATIONS[version]:
            conn.execute(statement)
        conn.execute("INSERT INTO _schema_version (version) VALUES (?)", (version,))
        conn.commit()
