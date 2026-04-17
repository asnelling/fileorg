from __future__ import annotations

from pathlib import Path

from fileorg.scanner.pipeline import run_scan
from fileorg.db.connection import get_connection
from fileorg.db import queries


def test_dry_run_scan(source_dir: Path, db_path: Path) -> None:
    result = run_scan(source_dir=source_dir, db_path=db_path, dry_run=True)
    assert result.status == "completed"
    assert result.processed >= 3

    conn = get_connection(db_path)
    total = queries.count_files(conn)
    categorized = queries.count_files(conn, "categorized")
    conn.close()
    assert total >= 3
    assert categorized == total


def test_resume_skips_categorized(source_dir: Path, db_path: Path) -> None:
    run_scan(source_dir=source_dir, db_path=db_path, dry_run=True)

    conn = get_connection(db_path)
    statuses_before = queries.get_all_file_statuses(conn)
    conn.close()

    progress_calls: list = []
    run_scan(
        source_dir=source_dir,
        db_path=db_path,
        dry_run=True,
        resume=True,
        progress_callback=lambda p: progress_calls.append(p),
    )

    # All files were already categorized — they should be skipped quickly
    conn = get_connection(db_path)
    statuses_after = queries.get_all_file_statuses(conn)
    conn.close()
    assert set(statuses_before.values()) == {"categorized"}
    assert set(statuses_after.values()) == {"categorized"}


def test_scan_creates_scan_run(source_dir: Path, db_path: Path) -> None:
    run_scan(source_dir=source_dir, db_path=db_path, dry_run=True)
    conn = get_connection(db_path)
    run = queries.get_last_scan_run(conn)
    conn.close()
    assert run is not None
    assert run["status"] == "completed"
    assert run["source_dir"] == str(source_dir)


def test_clues_inserted(source_dir: Path, db_path: Path) -> None:
    run_scan(source_dir=source_dir, db_path=db_path, dry_run=True)
    conn = get_connection(db_path)
    rows = conn.execute("SELECT COUNT(*) FROM clues").fetchone()
    conn.close()
    assert rows[0] > 0


def test_empty_files_skipped(tmp_path: Path, db_path: Path) -> None:
    d = tmp_path / "src"
    d.mkdir()
    (d / "empty.txt").write_bytes(b"")
    (d / "nonempty.txt").write_bytes(b"hello")
    run_scan(source_dir=d, db_path=db_path, dry_run=True)
    conn = get_connection(db_path)
    total = queries.count_files(conn)
    conn.close()
    assert total == 1
