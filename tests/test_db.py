from __future__ import annotations

from pathlib import Path

from fileorg.db.connection import get_connection
from fileorg.db import queries


def test_migration_idempotent(db_path: Path) -> None:
    conn = get_connection(db_path)
    get_connection(db_path)  # second open applies migrations again — should not error
    conn.close()


def test_wal_mode(conn) -> None:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_create_scan_run(conn) -> None:
    run_id = queries.create_scan_run(conn, "/tmp/test")
    conn.commit()
    assert isinstance(run_id, int) and run_id > 0
    run = queries.get_last_scan_run(conn)
    assert run is not None
    assert run["source_dir"] == "/tmp/test"
    assert run["status"] == "running"


def test_upsert_file_deduplication(conn) -> None:
    run_id = queries.create_scan_run(conn, "/tmp")
    conn.commit()
    id1 = queries.upsert_file(conn, "abc123", "/a/file.txt", run_id, 100)
    id2 = queries.upsert_file(conn, "abc123", "/b/file.txt", run_id, 100)
    conn.commit()
    assert id1 == id2
    row = queries.get_file_by_id(conn, id1)
    assert row["path"] == "/b/file.txt"


def test_insert_clues_idempotent(conn) -> None:
    run_id = queries.create_scan_run(conn, "/tmp")
    file_id = queries.upsert_file(conn, "xyz", "/f.txt", run_id, 10)
    queries.insert_clues(conn, file_id, "filename", [{"key": "ext", "value": "txt", "confidence": 1.0}])
    queries.insert_clues(conn, file_id, "filename", [{"key": "ext", "value": "txt", "confidence": 1.0}])
    conn.commit()
    clues = queries.get_clues_for_file(conn, file_id)
    assert len([c for c in clues if c["plugin_name"] == "filename"]) == 1


def test_get_or_create_category(conn) -> None:
    cat_id = queries.get_or_create_category(conn, "Documents/Legal")
    conn.commit()
    cat_id2 = queries.get_or_create_category(conn, "Documents/Legal")
    conn.commit()
    assert cat_id == cat_id2


def test_overview_stats_empty(conn) -> None:
    stats = queries.get_overview_stats(conn)
    assert stats["total_files"] == 0
    assert stats["categorized_pct"] == 0.0
