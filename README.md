# fileorg

A local-first file categorization tool. Point it at a messy archive and it scans every file, extracts clues via a plugin system, and uses a local AI model (Ollama) to assign each file a hierarchical category — all without touching the originals or sending data anywhere.

## Features

- **Local first** — no internet required; uses only local AI models via Ollama
- **Plugin architecture** — clues about files are produced by swappable plugins (filename, EXIF, OCR, archive contents, encryption detection)
- **Resumable** — interrupted scans pick up exactly where they left off
- **Safe** — original files are never modified; all data lives in a separate SQLite database
- **Web dashboard** — browse categories, search files, inspect clues, track encrypted volumes, and surface under-covered files
- **Spec-driven** — every component is specified in [`specs/`](specs/) before implementation

## Requirements

| Dependency | Purpose |
|------------|---------|
| Python 3.11+ | Runtime |
| [Ollama](https://ollama.com) | Local AI model runner |
| `tesseract-ocr` | OCR text extraction (optional) |
| `libmagic1` | Reliable MIME type detection |

Install system dependencies (Debian/Ubuntu):

```bash
sudo apt install tesseract-ocr libmagic1
```

Install and start Ollama, then pull a model:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2
```

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

### Scan a directory

```bash
fileorg scan --source /path/to/archive
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--source` | *(required)* | Directory to scan |
| `--dest` | `./fileorg-output` | Output directory for exports |
| `--db` | `./data/fileorg.db` | SQLite database path |
| `--model` | `llama3.2` | Ollama model name |
| `--plugins` | *(all)* | Comma-separated plugin names to enable |
| `--resume / --no-resume` | `--resume` | Resume a previous scan |
| `--dry-run` | `false` | Skip AI categorization |
| `--follow-symlinks` | `false` | Follow symbolic links |

### View the dashboard

```bash
fileorg dashboard
```

Opens a web UI at `http://127.0.0.1:8000` with:
- **Overview** — scan progress, summary stats, top categories, recently categorized files
- **Categories** — hierarchical category browser with file counts
- **Files** — paginated, searchable, filterable file table
- **Encrypted** — detected encrypted volumes with key status
- **Clueless** — files with low plugin coverage that may need attention

### Check status

```bash
fileorg status
```

### Export results

```bash
# Symlink tree (default) — browse categories in any file manager
fileorg export --dest ./sorted

# JSON manifest
fileorg export --dest ./out --format json

# CSV spreadsheet
fileorg export --dest ./out --format csv

# Filter to one category subtree
fileorg export --dest ./out --category "Photography/Travel"
```

### List plugins

```bash
fileorg plugins list
```

## How it works

```
scan --source <dir>
  │
  ├─ Walk directory (sorted, deterministic)
  ├─ SHA-256 hash each file (deduplication + resume key)
  ├─ Detect MIME type (python-magic)
  │
  ├─ Run plugins:
  │   ├─ filename   → extension, stem, tokens, parent dirs
  │   ├─ exif       → camera make/model, date taken, GPS, dimensions
  │   ├─ archive    → format, entry count, filenames inside, encryption
  │   ├─ ocr        → extracted text, word count, language
  │   └─ encryption → detect zip/7z/PGP/OpenSSL/VeraCrypt/KeePass
  │
  ├─ Score coverage (clueless plugin)
  │   └─ Files with score < 0.35 are flagged for review
  │
  └─ Ollama AI categorization
      └─ Clues → prompt → JSON response → category stored in DB
```

All state is committed to SQLite after every file. If the process is killed mid-scan, the next run with `--resume` (the default) skips already-categorized files and retries anything that didn't finish.

## Plugin system

Plugins implement a simple interface:

```python
class MyPlugin(CluePlugin):
    name = "myplugin"

    def accepts(self, path: Path, mime_type: str | None) -> bool:
        return mime_type == "application/x-my-format"

    def extract(self, path: Path) -> Sequence[Clue]:
        # never raise — catch exceptions and return an error Clue
        return [Clue(key="my_fact", value="...", confidence=0.9)]
```

Register it in `src/fileorg/plugins/registry.py` alongside the built-in plugins.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Specs for all components live in [`specs/`](specs/). When adding a new feature, write the spec first.

## Project structure

```
fileorg/
├── specs/                  # Component specs (read before implementing)
├── src/fileorg/
│   ├── cli.py              # Typer CLI entry point
│   ├── config.py           # AppConfig dataclass
│   ├── db/                 # SQLite connection, migrations, queries
│   ├── scanner/            # Walk → hash → plugin → AI pipeline
│   ├── plugins/            # CluePlugin ABC + all built-in plugins
│   ├── ai/                 # Ollama client + prompt templates
│   ├── dashboard/          # FastAPI app, routes, Jinja2 templates
│   └── export/             # Symlink / JSON / CSV exporter
└── tests/                  # pytest test suite
```
