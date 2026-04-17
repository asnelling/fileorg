# Spec: `check` Command

## Purpose

A diagnostic command that probes every local dependency fileorg relies on,
reports its status and version, and exits non-zero if any required dependency
is missing. Useful for confirming a new installation is ready and for
troubleshooting why a scan produced unexpected results (e.g. OCR skipped,
AI unavailable).

## Command signature

```
fileorg check
```

No options. Always checks all dependencies. Prints a Rich table to stdout.

## Dependencies to check

| Dependency | Kind | Required? | How to probe |
|------------|------|-----------|--------------|
| Python | runtime | yes | `sys.version` |
| `ollama` Python package | pip | yes | `importlib.metadata.version("ollama")` |
| Ollama daemon | system service | yes (for AI) | `ollama.list()` — connection error → not running |
| Ollama models | pulled models | yes (for AI) | `ollama.list()` response — list each model name + size |
| `python-magic` | pip | yes (for MIME) | `importlib.metadata.version("python-magic")` |
| `libmagic` (system) | system lib | yes (for MIME) | `magic.Magic()` instantiation — ImportError/OSError → missing |
| `Pillow` | pip | yes (EXIF/OCR) | `importlib.metadata.version("Pillow")` |
| `piexif` | pip | yes (EXIF) | `importlib.metadata.version("piexif")` |
| `pytesseract` | pip | yes (OCR) | `importlib.metadata.version("pytesseract")` |
| `tesseract` binary | system | yes (OCR) | `pytesseract.get_tesseract_version()` — FileNotFoundError → missing |
| `py7zr` | pip | yes (archives) | `importlib.metadata.version("py7zr")` |

## Output format

A single Rich table with columns: **Dependency**, **Status**, **Version / Detail**.

Status values:
- `ok` — green badge
- `not installed` — red badge
- `not running` — yellow badge (daemon up but unreachable)
- `no models` — yellow badge (daemon running, no models pulled)

Example output:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Dependency             ┃ Status         ┃ Version / Detail                  ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Python                 │ ok             │ 3.13.7                            │
│ ollama (package)       │ ok             │ 0.4.5                             │
│ Ollama daemon          │ ok             │ running                           │
│ Ollama models          │ ok             │ llama3.2:latest (2.0 GB)          │
│                        │                │ mistral:latest (4.1 GB)           │
│ python-magic           │ ok             │ 0.4.27                            │
│ libmagic (system)      │ ok             │ available                         │
│ Pillow                 │ ok             │ 10.4.0                            │
│ piexif                 │ ok             │ 1.1.3                             │
│ pytesseract (package)  │ ok             │ 0.3.10                            │
│ tesseract (binary)     │ ok             │ 5.3.4                             │
│ py7zr                  │ ok             │ 0.21.0                            │
└────────────────────────┴────────────────┴───────────────────────────────────┘
```

When a dependency is missing or unavailable:

```
│ Ollama daemon          │ not running    │ install: https://ollama.com       │
│ tesseract (binary)     │ not installed  │ apt install tesseract-ocr         │
│ libmagic (system)      │ not installed  │ apt install libmagic1             │
```

## Ollama model rows

If the daemon is running and models are available, each model gets its own
detail line within the Ollama models row (multi-line cell). Show:
`<name> (<size in GB, 1 decimal place>)`.

If the daemon is running but no models are pulled, show status `no models`
with detail `run: ollama pull llama3.2`.

## Exit code

- `0` if all **required** dependencies are present (daemon/models are not
  required for `--dry-run` scans, but the command still reports their status)
- `1` if any pip package or system library is missing

The Ollama daemon and models do not affect the exit code — their absence is
reported as a warning (yellow) since `--dry-run` scans work without them.

## Implementation

Add to `src/fileorg/cli.py` as a new `@app.command()` named `check`.

All probing logic lives inline in the command function — no separate module
needed. Each probe is wrapped in its own `try/except` so one failure does
not prevent the others from running.

## Testing

`tests/test_cli.py` (create if not present):
- Invoke `fileorg check` via Typer's `CliRunner`
- Assert exit code 0 when all pip packages are importable (mocking system
  calls for tesseract/libmagic/ollama)
- Assert exit code 1 when a pip package raises `PackageNotFoundError`
- Assert the output table contains all expected dependency names
