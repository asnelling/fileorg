from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── scan_runs ──────────────────────────────────────────────────────────────────

def create_scan_run(conn: sqlite3.Connection, source_dir: str) -> int:
    cur = conn.execute(
        "INSERT INTO scan_runs (started_at, source_dir, status) VALUES (?, ?, 'running')",
        (_now(), source_dir),
    )
    return cur.lastrowid  # type: ignore[return-value]


def finish_scan_run(
    conn: sqlite3.Connection, run_id: int, status: str, processed: int
) -> None:
    conn.execute(
        "UPDATE scan_runs SET finished_at=?, status=?, processed=? WHERE id=?",
        (_now(), status, processed, run_id),
    )


def update_scan_run_total(conn: sqlite3.Connection, run_id: int, total: int) -> None:
    conn.execute("UPDATE scan_runs SET total_files=? WHERE id=?", (total, run_id))


def get_last_scan_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()


# ── files ──────────────────────────────────────────────────────────────────────

def upsert_file(
    conn: sqlite3.Connection,
    sha256: str,
    path: str,
    run_id: int,
    size_bytes: int,
) -> int:
    conn.execute(
        """
        INSERT INTO files (sha256, path, first_seen_run, last_seen_run, size_bytes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(sha256) DO UPDATE SET
            path=excluded.path,
            last_seen_run=excluded.last_seen_run
        """,
        (sha256, path, run_id, run_id, size_bytes),
    )
    row = conn.execute("SELECT id FROM files WHERE sha256=?", (sha256,)).fetchone()
    return row["id"]


def update_file_mime(conn: sqlite3.Connection, file_id: int, mime_type: str) -> None:
    conn.execute("UPDATE files SET mime_type=? WHERE id=?", (mime_type, file_id))


def update_file_status(
    conn: sqlite3.Connection,
    file_id: int,
    status: str,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE files SET scan_status=?, error_message=? WHERE id=?",
        (status, error, file_id),
    )


def get_all_file_statuses(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT sha256, scan_status FROM files").fetchall()
    return {r["sha256"]: r["scan_status"] for r in rows}


def get_file_by_id(conn: sqlite3.Connection, file_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()


def list_files(
    conn: sqlite3.Connection,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
    sort: str = "size_desc",
) -> list[sqlite3.Row]:
    order = {
        "size_desc": "f.size_bytes DESC",
        "size_asc": "f.size_bytes ASC",
        "path_asc": "f.path ASC",
        "confidence_desc": "fc.confidence DESC",
    }.get(sort, "f.size_bytes DESC")

    conditions: list[str] = []
    params: list[object] = []

    if status:
        conditions.append("f.scan_status=?")
        params.append(status)
    if category:
        conditions.append("c.name LIKE ?")
        params.append(f"{category}%")
    if search:
        conditions.append("(f.path LIKE ? OR EXISTS (SELECT 1 FROM clues cl WHERE cl.file_id=f.id AND cl.value LIKE ?))")
        params.extend([f"%{search}%", f"%{search}%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit, offset])

    join = "LEFT JOIN file_categories fc ON f.id=fc.file_id LEFT JOIN categories c ON fc.category_id=c.id"
    sql = f"SELECT DISTINCT f.*, c.name AS category_name, fc.confidence AS cat_confidence FROM files f {join} {where} ORDER BY {order} LIMIT ? OFFSET ?"
    return conn.execute(sql, params).fetchall()


def count_files(conn: sqlite3.Connection, status: str | None = None) -> int:
    if status:
        row = conn.execute("SELECT COUNT(*) FROM files WHERE scan_status=?", (status,)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM files").fetchone()
    return row[0]


# ── clues ──────────────────────────────────────────────────────────────────────

def insert_clues(
    conn: sqlite3.Connection,
    file_id: int,
    plugin_name: str,
    clues: list[dict],
) -> None:
    conn.execute(
        "DELETE FROM clues WHERE file_id=? AND plugin_name=?", (file_id, plugin_name)
    )
    now = _now()
    conn.executemany(
        "INSERT INTO clues (file_id, plugin_name, key, value, confidence, created_at) VALUES (?,?,?,?,?,?)",
        [(file_id, plugin_name, c["key"], c["value"], c["confidence"], now) for c in clues],
    )


def get_clues_for_file(conn: sqlite3.Connection, file_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM clues WHERE file_id=? ORDER BY plugin_name, key", (file_id,)
    ).fetchall()


# ── categories ─────────────────────────────────────────────────────────────────

def get_or_create_category(conn: sqlite3.Connection, name: str) -> int:
    conn.execute(
        "INSERT INTO categories (name, created_at) VALUES (?, ?) ON CONFLICT(name) DO NOTHING",
        (name, _now()),
    )
    row = conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
    return row["id"]


def list_categories(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.id, c.name, COUNT(fc.file_id) AS file_count,
               COALESCE(SUM(f.size_bytes), 0) AS total_size
        FROM categories c
        LEFT JOIN file_categories fc ON c.id=fc.category_id
        LEFT JOIN files f ON fc.file_id=f.id
        GROUP BY c.id ORDER BY file_count DESC
        """
    ).fetchall()


# ── file_categories ────────────────────────────────────────────────────────────

def upsert_file_category(
    conn: sqlite3.Connection,
    file_id: int,
    category_id: int,
    confidence: float,
    model: str,
) -> None:
    conn.execute(
        """
        INSERT INTO file_categories (file_id, category_id, confidence, model_used, assigned_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(file_id, category_id) DO UPDATE SET
            confidence=excluded.confidence,
            model_used=excluded.model_used,
            assigned_at=excluded.assigned_at
        """,
        (file_id, category_id, confidence, model, _now()),
    )


def get_categories_for_file(conn: sqlite3.Connection, file_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.name, fc.confidence, fc.model_used, fc.assigned_at
        FROM file_categories fc JOIN categories c ON fc.category_id=c.id
        WHERE fc.file_id=? ORDER BY fc.confidence DESC
        """,
        (file_id,),
    ).fetchall()


# ── encrypted_volumes ──────────────────────────────────────────────────────────

def upsert_encrypted_volume(
    conn: sqlite3.Connection, file_id: int, volume_type: str
) -> None:
    conn.execute(
        """
        INSERT INTO encrypted_volumes (file_id, volume_type)
        VALUES (?, ?)
        ON CONFLICT(file_id) DO UPDATE SET volume_type=excluded.volume_type
        """,
        (file_id, volume_type),
    )


def list_encrypted_volumes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT ev.*, f.path, f.size_bytes
        FROM encrypted_volumes ev JOIN files f ON ev.file_id=f.id
        ORDER BY ev.key_discovered ASC, f.path ASC
        """
    ).fetchall()


def set_decryption_key(
    conn: sqlite3.Connection, file_id: int, key: str
) -> None:
    from datetime import datetime, timezone
    conn.execute(
        "UPDATE encrypted_volumes SET decryption_key=?, key_discovered=1, decrypted_at=? WHERE file_id=?",
        (key, datetime.now(timezone.utc).isoformat(), file_id),
    )


# ── plugin_coverage ────────────────────────────────────────────────────────────

def upsert_coverage(
    conn: sqlite3.Connection,
    file_id: int,
    plugin_count: int,
    total_confidence: float,
    clue_count: int,
    coverage_score: float,
    flagged: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO plugin_coverage
            (file_id, plugin_count, total_confidence, clue_count, coverage_score, flagged_clueless)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_id) DO UPDATE SET
            plugin_count=excluded.plugin_count,
            total_confidence=excluded.total_confidence,
            clue_count=excluded.clue_count,
            coverage_score=excluded.coverage_score,
            flagged_clueless=excluded.flagged_clueless
        """,
        (file_id, plugin_count, total_confidence, clue_count, coverage_score, int(flagged)),
    )


def list_clueless_files(
    conn: sqlite3.Connection, limit: int = 100
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT pc.*, f.path, f.mime_type, f.size_bytes
        FROM plugin_coverage pc JOIN files f ON pc.file_id=f.id
        WHERE pc.flagged_clueless=1
        ORDER BY pc.coverage_score ASC LIMIT ?
        """,
        (limit,),
    ).fetchall()


# ── dashboard stats ────────────────────────────────────────────────────────────

def get_overview_stats(conn: sqlite3.Connection) -> dict:
    total = count_files(conn)
    categorized = count_files(conn, "categorized")
    error = count_files(conn, "error")
    pending = count_files(conn, "pending") + count_files(conn, "clued")
    pct = round(100 * categorized / total, 1) if total else 0.0

    size_row = conn.execute("SELECT COALESCE(SUM(size_bytes),0) FROM files").fetchone()
    cat_count = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    enc_count = conn.execute("SELECT COUNT(*) FROM encrypted_volumes").fetchone()[0]
    clueless_count = conn.execute(
        "SELECT COUNT(*) FROM plugin_coverage WHERE flagged_clueless=1"
    ).fetchone()[0]

    top_cats = conn.execute(
        """
        SELECT c.name, COUNT(fc.file_id) AS file_count
        FROM categories c JOIN file_categories fc ON c.id=fc.category_id
        GROUP BY c.id ORDER BY file_count DESC LIMIT 8
        """
    ).fetchall()

    recent = conn.execute(
        """
        SELECT f.path, c.name AS category, fc.confidence
        FROM file_categories fc
        JOIN files f ON fc.file_id=f.id
        JOIN categories c ON fc.category_id=c.id
        ORDER BY fc.assigned_at DESC LIMIT 10
        """
    ).fetchall()

    last_run = get_last_scan_run(conn)

    return {
        "total_files": total,
        "categorized_count": categorized,
        "categorized_pct": pct,
        "error_count": error,
        "pending_count": pending,
        "total_size_bytes": size_row[0],
        "category_count": cat_count,
        "encrypted_count": enc_count,
        "clueless_count": clueless_count,
        "top_categories": [dict(r) for r in top_cats],
        "recent_files": [dict(r) for r in recent],
        "last_scan": dict(last_run) if last_run else None,
    }
