from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from fileorg.plugins.base import Clue, CluePlugin

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def _tokenize(stem: str) -> list[str]:
    stem = _CAMEL_RE.sub(" ", stem)
    tokens = re.split(r"[_\-.\s]+", stem)
    result = []
    for t in tokens:
        t = t.lower()
        if len(t) < 2:
            continue
        if t.isdigit() and not _YEAR_RE.match(t):
            continue
        result.append(t)
    return result


class FilenamePlugin(CluePlugin):
    name = "filename"

    def accepts(self, path: Path, mime_type: str | None) -> bool:
        return True

    def extract(self, path: Path) -> Sequence[Clue]:
        try:
            ext = path.suffix.lstrip(".").lower()
            stem = path.stem
            tokens = _tokenize(stem)
            parents = [p.name for p in path.parents if p.name][:3]

            clues: list[Clue] = [
                Clue(key="extension", value=ext or "", confidence=1.0),
                Clue(key="stem", value=stem, confidence=1.0),
            ]
            if tokens:
                clues.append(Clue(key="name_tokens", value=" ".join(tokens), confidence=0.9))
            if parents:
                clues.append(Clue(key="parent_dirs", value=" ".join(reversed(parents)), confidence=0.8))
            clues.append(Clue(key="depth", value=str(len(path.parts) - 1), confidence=1.0))
            return clues
        except Exception as e:
            return [Clue(key="plugin_error", value=str(e)[:200], confidence=0.0)]
