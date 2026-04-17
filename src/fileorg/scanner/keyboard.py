from __future__ import annotations

import queue
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class KeyCommand:
    key: str
    description: str
    handler: Callable[[], None]


class KeyboardController:
    def __init__(self) -> None:
        self._commands: dict[str, KeyCommand] = {}
        self._queue: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._running = False

    def register(self, key: str, description: str, handler: Callable[[], None]) -> None:
        self._commands[key] = KeyCommand(key=key, description=description, handler=handler)

    def commands(self) -> list[KeyCommand]:
        return list(self._commands.values())

    def start(self) -> None:
        if not sys.stdin.isatty():
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def poll(self) -> None:
        while True:
            try:
                key = self._queue.get_nowait()
                if cmd := self._commands.get(key):
                    cmd.handler()
            except queue.Empty:
                break

    def _read_loop(self) -> None:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while self._running:
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    ch = sys.stdin.read(1)
                    if ch:
                        self._queue.put(ch)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
