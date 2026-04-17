from __future__ import annotations

import sqlite3

from fileorg.plugins.base import Clue

_MIME_PLUGIN_HINTS: dict[str, str] = {
    "image/jpeg": "exif",
    "image/tiff": "exif",
    "image/png": "ocr",
    "image/webp": "ocr",
    "application/zip": "archive",
    "application/x-tar": "archive",
    "application/x-7z-compressed": "archive",
}


class CluelessPlugin:
    THRESHOLD_PLUGINS = 3
    THRESHOLD_CLUES = 10
    FLAGGED_THRESHOLD = 0.35

    def compute(
        self,
        file_id: int,
        clues: list[sqlite3.Row],
        mime_type: str | None,
    ) -> tuple[float, bool, list[Clue]]:
        active_plugins = {row["plugin_name"] for row in clues}
        # Exclude the clueless plugin itself from coverage scoring
        active_plugins.discard("clueless")
        real_clues = [r for r in clues if r["plugin_name"] != "clueless" and r["key"] != "plugin_error"]

        plugin_count = len(active_plugins)
        clue_count = len(real_clues)
        total_confidence = sum(r["confidence"] for r in real_clues)
        avg_confidence = total_confidence / clue_count if clue_count > 0 else 0.0

        score = min(
            1.0,
            0.5 * min(plugin_count / self.THRESHOLD_PLUGINS, 1.0)
            + 0.3 * min(clue_count / self.THRESHOLD_CLUES, 1.0)
            + 0.2 * avg_confidence,
        )
        flagged = score < self.FLAGGED_THRESHOLD

        extra: list[Clue] = [
            Clue(key="coverage_score", value=f"{score:.2f}", confidence=score)
        ]
        hint = self._suggest_plugin(mime_type, active_plugins)
        if hint:
            extra.append(Clue(key="missing_plugin_hint", value=hint, confidence=0.5))

        return score, flagged, extra

    def _suggest_plugin(self, mime_type: str | None, active_plugins: set[str]) -> str | None:
        if not mime_type:
            return None
        expected = _MIME_PLUGIN_HINTS.get(mime_type)
        if expected and expected not in active_plugins:
            return f"Consider enabling the '{expected}' plugin for {mime_type} files"
        return None
