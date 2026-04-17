from __future__ import annotations

import queue
from pathlib import Path
from unittest.mock import patch

import pytest

from fileorg.scanner.keyboard import KeyboardController


def _controller_with_key(key: str) -> KeyboardController:
    """Return a controller with `key` pre-loaded in its queue."""
    kb = KeyboardController()
    kb._queue.put(key)
    return kb


def test_registered_handler_is_called() -> None:
    called = []
    kb = _controller_with_key("f")
    kb.register("f", "skip file", lambda: called.append("f"))
    kb.poll()
    assert called == ["f"]


def test_unknown_key_is_ignored() -> None:
    kb = _controller_with_key("z")
    kb.register("f", "skip file", lambda: (_ for _ in ()).throw(AssertionError("should not call")))
    kb.poll()  # must not raise


def test_multiple_keys_dispatched_in_order() -> None:
    order = []
    kb = KeyboardController()
    kb._queue.put("f")
    kb._queue.put("d")
    kb.register("f", "skip file", lambda: order.append("f"))
    kb.register("d", "skip dir", lambda: order.append("d"))
    kb.poll()
    assert order == ["f", "d"]


def test_commands_returns_in_registration_order() -> None:
    kb = KeyboardController()
    kb.register("f", "skip file", lambda: None)
    kb.register("d", "skip dir", lambda: None)
    kb.register("?", "help", lambda: None)
    keys = [cmd.key for cmd in kb.commands()]
    assert keys == ["f", "d", "?"]


def test_register_overwrites_existing_key() -> None:
    results = []
    kb = _controller_with_key("f")
    kb.register("f", "first", lambda: results.append(1))
    kb.register("f", "second", lambda: results.append(2))
    kb.poll()
    assert results == [2]


def test_start_is_noop_when_not_a_tty() -> None:
    kb = KeyboardController()
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = False
        kb.start()
    assert kb._thread is None


def test_stop_sets_running_false() -> None:
    kb = KeyboardController()
    kb._running = True
    kb.stop()
    assert kb._running is False


def test_poll_empty_queue_does_nothing() -> None:
    kb = KeyboardController()
    kb.register("f", "skip file", lambda: (_ for _ in ()).throw(AssertionError()))
    kb.poll()  # queue is empty — handler must not be called


# ── integration: inject controller into run_scan ──────────────────────────────

def test_skip_file_leaves_file_as_pending(source_dir: Path, db_path: Path) -> None:
    from fileorg.scanner.pipeline import run_scan
    from fileorg.db.connection import get_connection
    from fileorg.db import queries

    kb = KeyboardController()
    # queue 'f' twice so the first two files are skipped
    kb._queue.put("f")
    kb._queue.put("f")

    result = run_scan(source_dir=source_dir, db_path=db_path, dry_run=True, keyboard_controller=kb)

    conn = get_connection(db_path)
    pending = queries.count_files(conn, "pending")
    conn.close()

    assert result.skipped_files >= 1
    assert pending >= 1


def test_skip_dir_bypasses_all_files_in_dir(tmp_path: Path, db_path: Path) -> None:
    from fileorg.scanner.pipeline import run_scan, ScanProgress
    from fileorg.db.connection import get_connection
    from fileorg.db import queries

    src = tmp_path / "src"
    src.mkdir()
    (src / "top.txt").write_text("top level")
    sub = src / "subdir"
    sub.mkdir()
    (sub / "a.txt").write_text("a")
    (sub / "b.txt").write_text("b")

    kb = KeyboardController()
    kb.register("d", "skip dir", lambda: None)  # registered so pipeline wires its own handler

    # Queue 'd' after the first file completes. At that moment current_dir is
    # `src` (parent of top.txt), so `src` is added to skip_dirs. All subsequent
    # files (subdir/a.txt, subdir/b.txt) are relative to `src` and are bypassed.
    calls = [0]

    def on_progress(p: ScanProgress) -> None:
        calls[0] += 1
        if calls[0] == 1:
            kb._queue.put("d")

    result = run_scan(source_dir=src, db_path=db_path, dry_run=True,
                      keyboard_controller=kb, progress_callback=on_progress)

    conn = get_connection(db_path)
    categorized = queries.count_files(conn, "categorized")
    conn.close()

    # Exactly one file (top.txt) was processed; the dir skip fired before the rest
    assert categorized == 1
    assert result.skipped_dirs == 1
