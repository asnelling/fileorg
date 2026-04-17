from __future__ import annotations

import sqlite3
from pathlib import Path

SYSTEM_PROMPT = """You are a file categorization assistant. You receive clues about a single file \
and assign it to the most specific applicable category using a slash-delimited hierarchy \
(e.g. "Photography/Travel/Europe" or "Documents/Legal/Contracts").

Rules:
- Return ONLY valid JSON. No markdown fences, no prose, no explanation outside JSON.
- Use exactly this schema: {"category": "<slash/delimited/path>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}
- Prefer specificity: "Documents/Legal/Contracts" over "Documents".
- Use title case for category components (e.g. "Photography" not "photography").
- If clues are insufficient, return category "Uncategorized" with confidence <= 0.2.
- Do not invent facts not present in the clues.
- confidence reflects how certain you are given the available evidence."""


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n //= 1024
    return f"{n:.0f} PB"


def build_user_prompt(
    path: Path,
    mime_type: str | None,
    clues: list[sqlite3.Row],
) -> str:
    parents = list(path.parts[-3:-1])
    path_hint = "/".join(parents + [path.name]) if parents else path.name

    try:
        size = path.stat().st_size
        size_str = _human_size(size)
    except OSError:
        size_str = "unknown"

    lines = [
        f"File: {path.name}",
        f"Path hint: {path_hint}",
        f"Size: {size_str}",
        f"MIME type: {mime_type or 'unknown'}",
        "",
        "Clues:",
    ]

    sorted_clues = sorted(clues, key=lambda r: (r["plugin_name"] == "clueless", r["plugin_name"], r["key"]))
    count = 0
    for row in sorted_clues:
        if count >= 30:
            break
        val = str(row["value"])
        if row["key"] == "coverage_score":
            suffix = " (low — limited information available)" if float(row["value"]) < 0.35 else ""
            lines.append(f"- [{row['plugin_name']}] {row['key']}: {val}{suffix}")
        else:
            if len(val) > 200:
                val = val[:197] + "..."
            lines.append(f"- [{row['plugin_name']}] {row['key']}: {val} (confidence: {row['confidence']:.2f})")
        count += 1

    lines.append("")
    lines.append("Categorize this file.")
    return "\n".join(lines)
