SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER NOT NULL
)
"""

SCAN_RUNS_TABLE = """
CREATE TABLE scan_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    source_dir  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',
    total_files INTEGER,
    processed   INTEGER DEFAULT 0
)
"""

FILES_TABLE = """
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
)
"""

CLUES_TABLE = """
CREATE TABLE clues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id     INTEGER NOT NULL REFERENCES files(id),
    plugin_name TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL
)
"""

CLUES_INDEX = """
CREATE INDEX idx_clues_file_plugin ON clues(file_id, plugin_name)
"""

CATEGORIES_TABLE = """
CREATE TABLE categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL
)
"""

FILE_CATEGORIES_TABLE = """
CREATE TABLE file_categories (
    file_id     INTEGER NOT NULL REFERENCES files(id),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    confidence  REAL NOT NULL DEFAULT 0.0,
    model_used  TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (file_id, category_id)
)
"""

ENCRYPTED_VOLUMES_TABLE = """
CREATE TABLE encrypted_volumes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id         INTEGER UNIQUE NOT NULL REFERENCES files(id),
    volume_type     TEXT NOT NULL,
    key_discovered  INTEGER NOT NULL DEFAULT 0,
    decryption_key  TEXT,
    decrypted_at    TEXT,
    notes           TEXT
)
"""

PLUGIN_COVERAGE_TABLE = """
CREATE TABLE plugin_coverage (
    file_id          INTEGER PRIMARY KEY REFERENCES files(id),
    plugin_count     INTEGER NOT NULL DEFAULT 0,
    total_confidence REAL NOT NULL DEFAULT 0.0,
    clue_count       INTEGER NOT NULL DEFAULT 0,
    coverage_score   REAL NOT NULL DEFAULT 0.0,
    flagged_clueless INTEGER NOT NULL DEFAULT 0
)
"""
