# fileorg — Agent Context

## What this project is

A local-first file categorization tool. It scans a directory, extracts clues about each file via a plugin system, uses a local Ollama AI model to assign each file a hierarchical category (e.g. `Photography/Travel/Europe`), and presents results via a FastAPI web dashboard. Original files are never modified.

## Development workflow

```bash
# Activate venv (always required)
source .venv/bin/activate

# Install (already done; re-run if pyproject.toml changes)
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run the CLI
fileorg --help
fileorg scan --source /path/to/dir --dry-run   # dry-run skips Ollama
fileorg status
fileorg dashboard                               # opens http://127.0.0.1:8000

# Verify Ollama is running (needed for non-dry-run scans)
ollama list
```

## Spec-driven development rule

**Always write a spec before implementing a new component.** Specs live in `specs/` numbered sequentially:

```
specs/01-database.md
specs/02-plugins.md
specs/03-scanner.md
specs/04-ai.md
specs/05-dashboard.md
specs/06-cli-and-export.md
```

When adding a feature, create `specs/07-feature-name.md` first. Each spec covers: purpose, file paths, interfaces, data shapes, error handling, and test plan.

## Architecture

```
src/fileorg/
├── cli.py                  # Typer CLI: scan, dashboard, status, export, plugins list
├── config.py               # AppConfig dataclass (all defaults live here)
├── db/
│   ├── connection.py       # get_connection(db_path) → sqlite3.Connection (WAL mode)
│   ├── migrations.py       # apply(conn) — versioned schema migrations
│   ├── models.py           # SQL CREATE TABLE strings (not ORM)
│   └── queries.py          # ALL SQL lives here; no inline SQL elsewhere
├── scanner/
│   ├── pipeline.py         # run_scan() — the main orchestrator
│   ├── walker.py           # walk(source_dir) → Iterator[Path]
│   ├── hasher.py           # sha256_file(path) → str
│   └── categorizer.py      # OllamaCategorizer — bridges pipeline ↔ AI client
├── plugins/
│   ├── base.py             # Clue dataclass + CluePlugin ABC
│   ├── registry.py         # PluginRegistry + build_default_registry()
│   ├── filename.py         # Always runs; extension, stem, tokens, parent dirs
│   ├── exif.py             # JPEG/TIFF/HEIC EXIF metadata via piexif
│   ├── archive.py          # zip/tar/7z entry listing; detects encrypted zips
│   ├── ocr.py              # pytesseract text extraction from images
│   ├── encryption.py       # Detects zip/7z/PGP/OpenSSL/VeraCrypt/KeePass
│   └── clueless.py         # Post-processing: coverage score, gap hints
├── ai/
│   ├── client.py           # OllamaClient — wraps ollama SDK; import as `_ollama`
│   └── prompts.py          # SYSTEM_PROMPT + build_user_prompt()
├── dashboard/
│   ├── app.py              # create_app(db_path) → FastAPI
│   ├── routes/             # overview, categories, files, encrypted, clueless, api
│   ├── templates/          # Jinja2 HTML (base, overview, categories, files, clues, encrypted, clueless)
│   └── static/             # style.css + htmx.min.js (bundled locally)
└── export/
    └── exporter.py         # run_export() — symlinks | json | csv
```

## Database schema (6 tables)

| Table | Key columns |
|-------|-------------|
| `scan_runs` | id, source_dir, status (`running`/`completed`/`interrupted`), total_files, processed |
| `files` | id, sha256 (UNIQUE — dedup key), path, size_bytes, mime_type, scan_status |
| `clues` | file_id, plugin_name, key, value, confidence — index on (file_id, plugin_name) |
| `categories` | id, name (UNIQUE, slash-delimited hierarchy) |
| `file_categories` | file_id, category_id, confidence, model_used |
| `encrypted_volumes` | file_id, volume_type, key_discovered, decryption_key |
| `plugin_coverage` | file_id, plugin_count, clue_count, coverage_score, flagged_clueless |

All queries go through `db/queries.py`. The connection is opened per-request; no shared state.

## Scanner pipeline stages (per file)

1. **Hash** — SHA-256; if already `categorized` in DB, skip all stages (resume)
2. **MIME** — python-magic with mimetypes fallback
3. **Plugins** — `accepts()` → `extract()` for each registered plugin; `_encrypted_volume_type` sentinel clue triggers `upsert_encrypted_volume()`
4. **Clueless** — `CluelessPlugin.compute()` writes `plugin_coverage`, appends `coverage_score` clue for AI
5. **AI** — `OllamaCategorizer` → `OllamaClient.categorize()` → upsert `categories` + `file_categories`

`conn.commit()` after every file. Errors per-file set `scan_status='error'` and continue.

## Resumability state machine

```
new → pending → clued → categorized
                  ↓           ↑
                error ────────┘  (retried on next --resume run)
```

- `--resume` (default): categorized files are skipped; clued files skip to stage 5
- `--no-resume`: resets pending/error rows; keeps categorized rows

## Plugin contract

```python
class MyPlugin(CluePlugin):
    name = "myplugin"                                    # stored in DB

    def accepts(self, path: Path, mime_type: str | None) -> bool: ...

    def extract(self, path: Path) -> Sequence[Clue]:
        # MUST NOT RAISE — catch all exceptions, return error Clue
        try:
            ...
        except Exception as e:
            return [Clue(key="plugin_error", value=str(e)[:200], confidence=0.0)]
```

Special sentinel: returning `Clue(key="_encrypted_volume_type", value="zip_encrypted")` signals the pipeline to call `upsert_encrypted_volume()`. The pipeline strips this clue before storing to DB.

Register new plugins in `src/fileorg/plugins/registry.py` → `build_default_registry()`.

## AI integration

- Default model: `llama3.2` (configurable via `--model`)
- `ollama` is imported as `_ollama` at module level in `ai/client.py` (enables mocking in tests)
- `format="json"` in `ollama.chat()` enforces JSON output; parse failures fall back to `{"category": "Uncategorized", "confidence": 0.0}`
- System prompt in `ai/prompts.py::SYSTEM_PROMPT`; user prompt built by `build_user_prompt(path, mime_type, clues)`

## Dashboard

FastAPI + Jinja2 + HTMX. Read-only — never triggers scans. Routes:

| Path | Template | Notes |
|------|----------|-------|
| `GET /` | overview.html | HTMX polls `/api/status` every 2s when scan is running |
| `GET /categories[/{name}]` | categories.html | |
| `GET /files` | files.html | `?q=`, `?status=`, `?category=`, `?page=`, `?sort=` |
| `GET /files/{id}` | clues.html | Per-file clue detail |
| `GET /encrypted` | encrypted.html | |
| `GET /clueless` | clueless.html | Sorted by coverage_score ASC |
| `GET /api/status` | JSON | Polled by HTMX |

## Tests

```
tests/
├── conftest.py          # db_path, conn, source_dir, zip_file, encrypted_zip fixtures
├── test_db.py           # migrations, queries
├── test_scanner.py      # dry-run, resume, error handling
├── test_categorizer.py  # OllamaClient (mocked via patch("fileorg.ai.client._ollama"))
└── test_plugins/
    ├── test_filename.py
    ├── test_archive.py
    └── test_encryption.py
```

32/32 passing as of initial build. The encrypted_zip fixture creates a ZIP with the encryption flag set via raw struct bytes (Python's zipfile module does not preserve flag_bits when writing).

## Known gaps / possible next steps

- `tests/test_plugins/test_exif.py` — needs a real JPEG with EXIF (or piexif-constructed bytes)
- `tests/test_plugins/test_ocr.py` — needs tesseract installed in CI
- Dashboard tests (`tests/test_dashboard.py`) — not yet written; use `httpx.TestClient(create_app(db_path))`
- `tests/test_exporter.py` — not yet written
- The `CluelessPlugin` thresholds (3 plugins, 10 clues, 0.35 score) are hardcoded; could be made configurable via `AppConfig`
- Archive plugin does not recursively scan archives inside archives (planned extension in PROJECT.md)
- Encryption plugin does not attempt decryption (by design); decryption key tracking is wired in DB but no UI to enter keys yet
- `AppConfig` is not loaded from a file; all values come from CLI flags (toml config file would be a natural next step)
