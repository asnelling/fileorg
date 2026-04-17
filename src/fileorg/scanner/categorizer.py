from __future__ import annotations

import sqlite3
from pathlib import Path

from fileorg.ai.client import OllamaClient
from fileorg.ai.prompts import build_user_prompt

_FALLBACK = {"category": "Uncategorized", "confidence": 0.0, "reasoning": ""}


class OllamaCategorizer:
    def __init__(self, model: str = "llama3.2") -> None:
        self.client = OllamaClient(model=model)

    def categorize(
        self,
        path: Path,
        mime_type: str | None,
        clues: list[sqlite3.Row],
    ) -> dict:
        try:
            prompt = build_user_prompt(path, mime_type, clues)
            return self.client.categorize(prompt)
        except Exception:
            return dict(_FALLBACK)
