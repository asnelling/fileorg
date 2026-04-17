# Spec: Database Module

## Purpose

Provides a local SQLite database for storing all scan results, file metadata, clues, categories, and coverage data. The database is the single source of truth — the scanner writes to it, the dashboard reads from it, and the exporter queries it.

## Requirements

- SQLite with WAL (Write-Ahead Logging) mode enabled for concurrent read/write access
- Schema versioned via a migrations table; new schema versions apply automatically on startup
- All queries centralized in `queries.py` — no inline SQL elsewhere in the codebase
- Connection factory accepts a path; returns a standard `sqlite3.Connection`
- Thread safety: each call site obtains its own connection; no shared connection state

## Files

### `src/fileorg/db/connection.py`

Exports:
- `get_connection(db_path: Path) -> sqlite3.Connection`
  - Opens (or creates) the SQLite file at `db_path`
  - Sets `PRAGMA journal_mode=WAL`
  - Sets `PRAGMA foreign_keys=ON`
  - Sets `row_factory = sqlite3.Row` for dict-like row access
  - Runs `migrations.apply(conn)` before returning
  - Caller is responsible for `conn.close()`

### `src/fileorg/db/migrations.py`

Versioned schema migrations applied in order. Each migration is a plain SQL string keyed by an integer version number.

Exports:
- `apply(conn: sqlite3.Connection) -> None`
  - Creates `_schema_version` table if missing
  - Reads current version (0 if table is empty)
  - Applies all migrations with version > current in ascending order
  - Commits after all migrations

Migration 1 creates all six tables (see schema below).

### `src/fileorg/db/models.py`

Documents the schema as Python constants (SQL CREATE TABLE strings). Used by migrations. Not an ORM — no classes represent rows.

### `src/fileorg/db/queries.py`

All named query functions. Each accepts a `conn: sqlite3.Connection` and typed parameters. Returns `sqlite3.Row` objects or Python primitives.

Required functions (minimum):

**scan_runs:**
- `create_scan_run(conn, source_dir: str) -> int` — inserts a new run, returns id
- `finish_scan_run(conn, run_id: int, status: str, processed: int) -> None`
- `get_last_scan_run(conn) -> sqlite3.Row | None`

**files:**
- `upsert_file(conn, sha256: str, path: str, run_id: int, size_bytes: int) -> int` — returns file id
- `update_file_mime(conn, file_id: int, mime_type: str) -> None`
- `update_file_status(conn, file_id: int, status: str, error: str | None = None) -> None`
- `get_all_file_statuses(conn) -> dict[str, str]` — returns {sha256: scan_status} for resume logic
- `get_file_by_id(conn, file_id: int) -> sqlite3.Row | None`
- `list_files(conn, status: str | None, category: str | None, search: str | None, offset: int, limit: int) -> list[sqlite3.Row]`
- `count_files(conn, status: str | None) -> int`

**clues:**
- `insert_clues(conn, file_id: int, plugin_name: str, clues: list[dict]) -> None` — bulk insert; deletes existing clues for (file_id, plugin_name) first
- `get_clues_for_file(conn, file_id: int) -> list[sqlite3.Row]`

**categories:**
- `get_or_create_category(conn, name: str) -> int` — returns category id
- `list_categories(conn) -> list[sqlite3.Row]`

**file_categories:**
- `upsert_file_category(conn, file_id: int, category_id: int, confidence: float, model: str) -> None`
- `get_categories_for_file(conn, file_id: int) -> list[sqlite3.Row]`

**encrypted_volumes:**
- `upsert_encrypted_volume(conn, file_id: int, volume_type: str) -> None`
- `list_encrypted_volumes(conn) -> list[sqlite3.Row]`
- `set_decryption_key(conn, file_id: int, key: str) -> None`

**plugin_coverage:**
- `upsert_coverage(conn, file_id: int, plugin_count: int, total_confidence: float, clue_count: int, coverage_score: float, flagged: bool) -> None`
- `list_clueless_files(conn, limit: int) -> list[sqlite3.Row]` — ordered by coverage_score ASC

**stats (for dashboard overview):**
- `get_overview_stats(conn) -> dict` — returns counts, percentages, and top categories

## Schema

### `_schema_version`
```sql
CREATE TABLE _schema_version (
    version INTEGER NOT NULL
);
```

### `scan_runs`
```sql
CREATE TABLE scan_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    source_dir  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    total_files INTEGER,
    processed   INTEGER DEFAULT 0
);
```

### `files`
```sql
CREATE TABLE files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256          TEXT UNIQUE NOT NULL,
    path            TEXT NOT NULL,
    first_seen_run  INTEGER REFERENCES scan_runs(id),
    last_seen_run   INTEGER REFERENCES scan_runs(id),
    size_bytes      INTEGER NOT NULL,
    mime_type       TEXT,
    scan_status     TEXT NOT NULL DEFAULT 'pending',
    error_message   TEXT
);
```

### `clues`
```sql
CREATE TABLE clues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id     INTEGER NOT NULL REFERENCES files(id),
    plugin_name TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_clues_file_plugin ON clues(file_id, plugin_name);
```

### `categories`
```sql
CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL
);
```

### `file_categories`
```sql
CREATE TABLE file_categories (
    file_id     INTEGER NOT NULL REFERENCES files(id),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    confidence  REAL NOT NULL DEFAULT 0.0,
    model_used  TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (file_id, category_id)
);
```

### `encrypted_volumes`
```sql
CREATE TABLE encrypted_volumes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id         INTEGER UNIQUE NOT NULL REFERENCES files(id),
    volume_type     TEXT NOT NULL,
    key_discovered  INTEGER NOT NULL DEFAULT 0,
    decryption_key  TEXT,
    decrypted_at    TEXT,
    notes           TEXT
);
```

### `plugin_coverage`
```sql
CREATE TABLE plugin_coverage (
    file_id          INTEGER PRIMARY KEY REFERENCES files(id),
    plugin_count     INTEGER NOT NULL DEFAULT 0,
    total_confidence REAL NOT NULL DEFAULT 0.0,
    clue_count       INTEGER NOT NULL DEFAULT 0,
    coverage_score   REAL NOT NULL DEFAULT 0.0,
    flagged_clueless INTEGER NOT NULL DEFAULT 0
);
```

## Error Handling

- All query functions propagate `sqlite3.Error` to callers — the pipeline handles these by marking the file as `error`
- `upsert_file` uses `INSERT OR IGNORE` followed by `UPDATE` to handle the duplicate sha256 case
- `insert_clues` runs `DELETE FROM clues WHERE file_id=? AND plugin_name=?` before bulk insert to ensure idempotency on resume

## Testing

- `tests/test_db.py` uses `tmp_path` fixture to create a fresh DB for each test
- Test `apply()` is idempotent (calling twice does not error)
- Test each query function with known data
- Test that WAL mode is set after `get_connection()`
