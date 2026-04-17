from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppConfig:
    db_path: Path = Path("data/fileorg.db")
    model: str = "llama3.2"
    dest_dir: Path = Path("fileorg-output")
    enabled_plugins: list[str] = field(default_factory=list)
    follow_symlinks: bool = False
    clueless_threshold: float = 0.35
    clueless_threshold_plugins: int = 3
    clueless_threshold_clues: int = 10
