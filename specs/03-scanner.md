# Spec: Scanner Pipeline

## Purpose

The scanner walks a source directory, processes each file through a sequence of stages (hash → MIME detect → plugins → coverage → AI categorize), and stores results in the database. It is designed to be resumable: if interrupted, it picks up where it left off on the next run.

## Files

### `src/fileorg/scanner/walker.py`

Yields file paths from a source directory.

```python
def walk(source_dir: Path, follow_symlinks: bool = False) -> Iterator[Path]:
    """
    Yields absolute Path objects for every regular file under source_dir.
    - Uses os.walk() with topdown=True, sorted directory entries for determinism
    - Skips symlinks unless follow_symlinks=True
    - Skips files with size 0 (empty files carry no meaningful clues)
    - Skips the database file itself if it happens to be inside source_dir
    """
```

### `src/fileorg/scanner/hasher.py`

```python
def sha256_file(path: Path, chunk_size: int = 65536) -> str:
    """
    Returns the hex SHA-256 digest of the file at path.
    Reads in chunks to avoid loading large files into memory.
    Raises OSError if the file cannot be read.
    """
```

### `src/fileorg/scanner/pipeline.py`

The orchestrator. Imports from all other modules.

```python
@dataclass
class ScanProgress:
    run_id: int
    total: int
    processed: int
    current_file: str
    status: str  # 'running' | 'completed' | 'interrupted'

def run_scan(
    source_dir: Path,
    db_path: Path,
    model: str = "llama3.2",
    enabled_plugins: list[str] | None = None,
    resume: bool = True,
    dry_run: bool = False,
    progress_callback: Callable[[ScanProgress], None] | None = None,
) -> ScanProgress:
    """
    Runs the full scan pipeline. Blocking — runs to completion.
    progress_callback is called after each file is processed.
    Returns final ScanProgress when done.
    """
```

#### Pipeline Stages (per file)

**Initialization (before the file loop):**
1. Open DB connection with `get_connection(db_path)`
2. Create scan run: `queries.create_scan_run(conn, str(source_dir))`
3. If `resume=True`: load `known = queries.get_all_file_statuses(conn)` → `dict[sha256, status]`
4. If `resume=False`: mark all `pending`/`error` statuses as reset (re-process them)
5. Count total files by walking once: `total = sum(1 for _ in walk(source_dir))`
6. Update `scan_runs.total_files = total`
7. Instantiate `registry = build_default_registry(enabled_plugins)`
8. Instantiate `categorizer = OllamaCategorizier(model=model)` (skip if `dry_run`)
9. Instantiate `clueless_plugin = CluelessPlugin()`

**Per-file loop** (`for path in walk(source_dir)`):

**Stage 2 — Hash:**
```
sha256 = sha256_file(path)
if resume and known.get(sha256) == 'categorized':
    queries.upsert_file(conn, sha256, str(path), run_id, stat.st_size)  # update last_seen_run
    conn.commit()
    continue  # skip all remaining stages
file_id = queries.upsert_file(conn, sha256, str(path), run_id, stat.st_size)
```

**Stage 3 — MIME:**
```
mime_type = detect_mime(path)   # python-magic with mimetypes fallback
queries.update_file_mime(conn, file_id, mime_type)
queries.update_file_status(conn, file_id, 'pending')
```

**Stage 4 — Plugins:**
```
active = registry.enabled(enabled_plugins)
for plugin in active:
    if plugin.accepts(path, mime_type):
        clues = plugin.extract(path)
        # Handle _encrypted_volume_type sentinel clue:
        encrypted_type = next((c.value for c in clues if c.key == '_encrypted_volume_type'), None)
        clues = [c for c in clues if c.key != '_encrypted_volume_type']
        if encrypted_type:
            queries.upsert_encrypted_volume(conn, file_id, encrypted_type)
        queries.insert_clues(conn, file_id, plugin.name, [
            {'key': c.key, 'value': c.value, 'confidence': c.confidence}
            for c in clues
        ])
queries.update_file_status(conn, file_id, 'clued')
```

**Stage 4.5 — Clueless:**
```
all_clues = queries.get_clues_for_file(conn, file_id)
score, flagged, extra_clues = clueless_plugin.compute(file_id, all_clues, mime_type)
queries.upsert_coverage(conn, file_id, ...)
queries.insert_clues(conn, file_id, 'clueless', [
    {'key': c.key, 'value': c.value, 'confidence': c.confidence}
    for c in extra_clues
])
```

**Stage 5 — AI (skipped if dry_run):**
```
if known.get(sha256) == 'clued':
    # Resume: re-use existing clues, only redo AI
    all_clues = queries.get_clues_for_file(conn, file_id)

result = categorizer.categorize(path, mime_type, all_clues)
category_id = queries.get_or_create_category(conn, result['category'])
queries.upsert_file_category(conn, file_id, category_id, result['confidence'], model)
queries.update_file_status(conn, file_id, 'categorized')
```

**After every file:**
```
conn.commit()
processed += 1
if progress_callback:
    progress_callback(ScanProgress(run_id, total, processed, str(path), 'running'))
```

**After file loop:**
```
queries.finish_scan_run(conn, run_id, 'completed', processed)
conn.commit()
conn.close()
```

**Error handling per file:**
Any unhandled exception during stages 2–5 for a file:
```
queries.update_file_status(conn, file_id, 'error', str(e)[:500])
conn.commit()
continue  # move to next file; do not abort scan
```

### `src/fileorg/scanner/categorizer.py`

Thin bridge between the pipeline and the AI client.

```python
class OllamaCategorizer:
    def __init__(self, model: str = "llama3.2") -> None: ...

    def categorize(
        self,
        path: Path,
        mime_type: str | None,
        clues: list[sqlite3.Row],
    ) -> dict:
        """
        Builds a prompt from path + mime_type + clues, calls Ollama,
        returns {'category': str, 'confidence': float, 'reasoning': str}.
        On any failure returns {'category': 'Uncategorized', 'confidence': 0.0, 'reasoning': ''}.
        """
        prompt = build_user_prompt(path, mime_type, clues)
        return self.client.categorize(prompt)
```

### MIME detection helper (in `pipeline.py` or a small utility)

```python
def detect_mime(path: Path) -> str | None:
    try:
        import magic
        return magic.from_file(str(path), mime=True)
    except Exception:
        import mimetypes
        return mimetypes.guess_type(str(path))[0]
```

## Resumability State Machine

```
[not in DB] ──→ pending ──→ clued ──→ categorized
                   ↓                      ↑
                 error ────────────────────┘ (retried on next --resume run)
```

On `--resume` (default):
- `categorized` files: update `last_seen_run` only, skip all stages
- `clued` files: skip stages 2–4, redo stage 5 (AI) only
- `pending` / `error` / new files: full pipeline

On `--no-resume`:
- Reset all `pending` and `error` rows to be reprocessed
- Keep `categorized` rows (expensive AI work is preserved)

## Concurrency

Single-threaded by design. The pipeline loop is sequential. The dashboard can read the DB concurrently due to WAL mode — no locking needed.

The keyboard controller (see below) runs its stdin reader in a daemon thread, but all state mutations it triggers happen on the main thread via `poll()`. No shared mutable state is accessed from both threads simultaneously.

## Progress Reporting

The `progress_callback` receives a `ScanProgress` after every committed file. The CLI uses this to update a Rich progress bar. The dashboard's `/api/status` endpoint reads `scan_runs` directly from the DB (the latest `running` run's `processed` / `total_files` columns).

## Interactive Keyboard Control

### `src/fileorg/scanner/keyboard.py`

While a scan is running, the user can press single keys to control pipeline behaviour without pressing Enter. This is implemented by a background thread that reads stdin in `cbreak` mode and enqueues keystrokes for the main pipeline thread to dispatch.

#### Design principles

- **Command registry**: commands are registered as `key → (description, handler)` before the scan starts. Adding a new command requires only one `register()` call — no changes to the dispatch loop.
- **Main-thread dispatch**: handlers are called from the main pipeline thread via `poll()`, never from the reader thread. This avoids all threading concerns around shared state.
- **TTY guard**: if stdin is not a TTY (piped input, CI), `start()` is a no-op. `poll()` always works and simply finds nothing.
- **Clean teardown**: the reader thread is a daemon and exits automatically when the process ends. `stop()` signals it to exit early (e.g. when the scan completes).

#### Interface

```python
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class KeyCommand:
    key: str
    description: str   # shown in the help line (e.g. "skip file")
    handler: Callable[[], None]


class KeyboardController:
    def register(self, key: str, description: str, handler: Callable[[], None]) -> None:
        """Register a single-character command. Overwrites any existing binding for key."""
        ...

    def commands(self) -> list[KeyCommand]:
        """Return registered commands in registration order (for display)."""
        ...

    def start(self) -> None:
        """
        Start the background stdin reader thread.
        No-op if stdin is not a TTY.
        Sets terminal to cbreak mode so each keypress is read immediately.
        Restores original terminal settings on stop() or process exit.
        """
        ...

    def stop(self) -> None:
        """Signal the reader thread to exit and restore terminal settings."""
        ...

    def poll(self) -> None:
        """
        Dispatch all pending keystrokes by calling their registered handlers.
        Must be called from the main thread.
        Unknown keys are silently ignored.
        """
        ...
```

#### Implementation notes

- Use `termios` + `tty.setcbreak(fd)` to read characters without waiting for Enter
- Use `select.select([sys.stdin], [], [], 0.1)` inside the reader loop to avoid a tight spin and allow the `_running` flag to be checked every 100 ms
- Store keystrokes in a `queue.SimpleQueue[str]` — `put()` from the reader thread, `get_nowait()` in `poll()` on the main thread
- Save and restore the original `termios` settings in a `finally` block so the terminal is not left in cbreak mode if the scan crashes

### Built-in keyboard commands

| Key | Action |
|-----|--------|
| `f` | Skip the current file: mark it `pending` in the DB (so it is retried on next resume) and continue to the next file |
| `d` | Skip the current directory: add `path.parent` to a `skip_dirs` set; all subsequent files whose path starts with that directory are skipped |
| `?` | Print registered commands to the console without interrupting the progress display |

### Pipeline integration

In `run_scan()`:

```python
skip_dirs: set[Path] = set()
_skip_file = [False]   # mutable container so closures can write to it
current_dir: Path = source_dir

kb = KeyboardController()
kb.register('f', 'skip file',      lambda: _skip_file.__setitem__(0, True))
kb.register('d', 'skip directory', lambda: skip_dirs.add(current_dir))
kb.register('?', 'show commands',  lambda: _print_commands(kb, console))
kb.start()
```

`run_scan()` signature gains a `keyboard_controller: KeyboardController | None = None` parameter so callers (tests, API consumers) can inject a custom or no-op controller. When `None`, a default `KeyboardController` is instantiated internally.

**Per-file loop changes:**

```python
for path in walk(source_dir, ...):
    current_dir = path.parent
    _skip_file[0] = False
    kb.poll()                              # dispatch any queued keys

    # Skip directory check
    if any(path.is_relative_to(d) for d in skip_dirs):
        continue

    # ... Stage 2 (Hash) ...

    kb.poll()
    if _skip_file[0]:
        queries.update_file_status(conn, file_id, 'pending')
        conn.commit()
        continue

    # ... Stage 3 (MIME) ...

    kb.poll()
    if _skip_file[0]:
        queries.update_file_status(conn, file_id, 'pending')
        conn.commit()
        continue

    # ... Stages 4, 4.5, 5 each preceded by kb.poll() + skip check ...
```

`kb.poll()` is called before each expensive stage so `f` takes effect as soon as the current stage finishes, not only between files.

**After the file loop:**

```python
kb.stop()
```

### CLI display

The Rich progress bar description includes a static hint line showing registered commands:

```
[cyan]photo_001.jpg[/cyan]  [dim]f=skip file  d=skip dir  ?=help[/dim]
```

### Skipped file behaviour

- **`f` (skip file)**: file is left as `pending` in the DB. On the next `--resume` run it will be processed normally. A counter of skipped files is shown in the post-scan summary.
- **`d` (skip directory)**: files in that directory are silently bypassed (no DB record created if they have not been seen before; already-seen files are left at their current status). The directory path is logged to the console at INFO level.

## Testing

`tests/test_scanner.py`:
- Create a temp directory with known files
- Run `run_scan()` with `dry_run=True` — verify files table populated, clues inserted
- Run again — verify resume skips already-categorized files
- Verify `scan_runs` row has correct counts and status
- Test that a plugin error on one file does not abort the scan (check `error_message` set)

`tests/test_keyboard.py`:
- Test `poll()` calls registered handler when a key is in the queue
- Test unknown keys are silently ignored
- Test `commands()` returns commands in registration order
- Test `start()` is a no-op when stdin is not a TTY (patch `sys.stdin.isatty`)
- Test `stop()` sets `_running = False` (reader thread exits within 200 ms)
- Integration: inject a pre-populated `KeyboardController` into `run_scan()` to simulate `f` and `d` keypresses and verify files/directories are skipped correctly
