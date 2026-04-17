from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass
class Clue:
    key: str
    value: str
    confidence: float = 1.0
    raw: dict = field(default_factory=dict)


class CluePlugin(ABC):
    name: str

    @abstractmethod
    def accepts(self, path: Path, mime_type: str | None) -> bool:
        ...

    @abstractmethod
    def extract(self, path: Path) -> Sequence[Clue]:
        ...

    def __repr__(self) -> str:
        return f"<Plugin:{self.name}>"
