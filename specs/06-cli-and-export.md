# Spec: CLI and Export Module

## Purpose

The CLI is the primary user-facing interface. It wires together the scanner, dashboard, and exporter into a coherent set of commands. The exporter materializes scan results as symlinks, JSON, or CSV — without touching the original files.

## Files

### `src/fileorg/__main__.py`

```python
from fileorg.cli import app
app()
```

Enables `python -m fileorg`.

### `src/fileorg/config.py`

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class AppConfig:
    db_path: Path = Path("data/fileorg.db")
    model: str = "llama3.2"
    dest_dir: Path = Path("fileorg-output")
    enabled_plugins: list[str] = field(default_factory=list)  # empty = all
    follow_symlinks: bool = False
    clueless_threshold: float = 0.35
    clueless_threshold_plugins: int = 3
    clueless_threshold_clues: int = 10
```

Config is not loaded from a file in v1 — all values come from CLI flags with these defaults.

### `src/fileorg/cli.py`

Built with **Typer**. Uses `rich.console.Console` for output.

```python
import typer
app = typer.Typer(help="fileorg — local file categorization tool")
```

#### `fileorg scan`

```
fileorg scan --source <dir>
             [--dest <dir>]        # default: ./fileorg-output
             [--db <path>]         # default: ./data/fileorg.db
             [--model <name>]      # default: llama3.2
             [--plugins <list>]    # comma-separated plugin names; default: all
             [--resume/--no-resume]  # default: --resume
             [--dry-run]           # skip AI stage; default: False
             [--follow-symlinks]   # default: False
```

Implementation:
1. Validate `--source` exists and is a directory
2. Create `db_path.parent` if needed
3. Warn if Ollama unavailable (unless `--dry-run`)
4. Create Rich `Progress` with two bars: file count + current filename
5. Call `run_scan(...)` with progress_callback updating the Progress bars
6. Print final summary table when done

Output example:
```
Scanning /mnt/archive...
[████████████████████] 1204/1204 files
✓ Scan complete in 3m 42s
  Files scanned:   1204
  Categorized:     1198 (99.5%)
  Errors:          6
  Clueless flagged: 12
  Categories found: 47
```

#### `fileorg dashboard`

```
fileorg dashboard [--db <path>] [--host 127.0.0.1] [--port 8000]
```

Implementation:
1. Validate `db_path` exists
2. Print "Dashboard running at http://<host>:<port> — Ctrl+C to stop"
3. Call `uvicorn.run(create_app(db_path), host=host, port=port)`

#### `fileorg status`

```
fileorg status [--db <path>]
```

Prints a Rich table to stdout:

```
┌─ fileorg status ─────────────────────────────┐
│ Last scan:     2026-04-16 20:13  (completed) │
│ Source:        /mnt/archive                  │
│ Total files:   1,204                         │
│ Categorized:   1,198 (99.5%)                 │
│ Errors:        6                             │
│ Pending:       0                             │
│ Categories:    47                            │
│ Encrypted:     3  (0 keys found)             │
│ Clueless:      12                            │
└──────────────────────────────────────────────┘
```

If no DB exists: print "No scan database found at <path>. Run `fileorg scan` first."

#### `fileorg export`

```
fileorg export --dest <dir>
               [--db <path>]
               [--format symlinks|json|csv]  # default: symlinks
               [--category <filter>]         # optional subtree filter
```

Calls `run_export(db_path, dest_dir, format, category_filter)`.

#### `fileorg plugins list`

```
fileorg plugins list
```

Prints a Rich table listing all registered plugins with their name, description, and supported MIME type patterns.

### `src/fileorg/export/exporter.py`

```python
def run_export(
    db_path: Path,
    dest_dir: Path,
    format: str = "symlinks",
    category_filter: str | None = None,
) -> Path:
    """
    Materializes scan results. Returns path to output directory or file.
    Never touches source files.
    """
```

#### Symlinks mode (default)

For each file in `file_categories` (filtered by `category_filter` if set):
1. Determine category path: split `category.name` on `/` → directory components
2. Create `dest_dir / category_path_components / filename`
3. `os.symlink(original_path, dest_path)` — absolute symlinks
4. If `dest_path` already exists (from prior export): skip with warning
5. Print progress with Rich

Result: `dest_dir/Photography/Travel/Europe/IMG_1234.jpg → /mnt/archive/photos/IMG_1234.jpg`

#### JSON mode

Single `dest_dir/manifest.json`:
```json
[
  {
    "file_id": 42,
    "sha256": "abc...",
    "path": "/mnt/archive/...",
    "size_bytes": 245120,
    "mime_type": "image/jpeg",
    "category": "Photography/Travel/Europe",
    "confidence": 0.87,
    "clues": [
      {"plugin": "exif", "key": "date_taken", "value": "2023-09-15", "confidence": 1.0},
      ...
    ]
  },
  ...
]
```

#### CSV mode

Single `dest_dir/manifest.csv` with columns:
`file_id, sha256, path, size_bytes, mime_type, category, confidence, scan_status`

One row per file. Clues not included in CSV (use JSON for full detail).

## Testing

`tests/test_cli.py` using Typer's `CliRunner`:
- Test `fileorg scan --source <tmp_dir> --dry-run` exits 0 and creates DB
- Test `fileorg status --db <tmp_db>` prints expected table
- Test `fileorg plugins list` lists at least 5 plugins
- Test `fileorg export --dest <tmp_dir> --format json` creates `manifest.json`

`tests/test_exporter.py`:
- Test symlinks mode creates correct directory structure
- Test JSON mode creates valid JSON
- Test CSV mode creates valid CSV with correct columns
- Test `--category` filter limits output
