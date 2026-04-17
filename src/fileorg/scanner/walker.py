from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator


def walk(source_dir: Path, follow_symlinks: bool = False, skip_path: Path | None = None) -> Iterator[Path]:
    for root, dirs, files in os.walk(str(source_dir), followlinks=follow_symlinks):
        dirs.sort()
        files.sort()
        for filename in files:
            path = Path(root) / filename
            if not follow_symlinks and path.is_symlink():
                continue
            if skip_path and path == skip_path:
                continue
            try:
                if path.stat().st_size == 0:
                    continue
            except OSError:
                continue
            yield path
