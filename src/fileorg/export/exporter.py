from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from fileorg.db.connection import get_connection
from fileorg.db import queries


def run_export(
    db_path: Path,
    dest_dir: Path,
    format: str = "symlinks",
    category_filter: str | None = None,
) -> Path:
    conn = get_connection(db_path)
    rows = queries.list_files(conn, category=category_filter, limit=100_000)

    if format == "symlinks":
        return _export_symlinks(rows, dest_dir, conn)
    elif format == "json":
        return _export_json(rows, dest_dir, conn)
    elif format == "csv":
        return _export_csv(rows, dest_dir)
    else:
        raise ValueError(f"Unknown format: {format}")


def _export_symlinks(rows: list, dest_dir: Path, conn) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    skipped = 0
    for row in rows:
        category = row["category_name"] or "Uncategorized"
        parts = category.split("/")
        target_dir = dest_dir.joinpath(*parts)
        target_dir.mkdir(parents=True, exist_ok=True)
        src = Path(row["path"])
        dst = target_dir / src.name
        if dst.exists() or dst.is_symlink():
            skipped += 1
            continue
        try:
            os.symlink(src.resolve(), dst)
        except OSError:
            pass
    conn.close()
    return dest_dir


def _export_json(rows: list, dest_dir: Path, conn) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_file = dest_dir / "manifest.json"
    records = []
    for row in rows:
        file_id = row["id"]
        clues = queries.get_clues_for_file(conn, file_id)
        records.append({
            "file_id": file_id,
            "sha256": row["sha256"],
            "path": row["path"],
            "size_bytes": row["size_bytes"],
            "mime_type": row["mime_type"],
            "category": row["category_name"],
            "confidence": row["cat_confidence"],
            "scan_status": row["scan_status"],
            "clues": [
                {"plugin": c["plugin_name"], "key": c["key"], "value": c["value"], "confidence": c["confidence"]}
                for c in clues
            ],
        })
    conn.close()
    out_file.write_text(json.dumps(records, indent=2))
    return out_file


def _export_csv(rows: list, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_file = dest_dir / "manifest.csv"
    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "file_id", "sha256", "path", "size_bytes", "mime_type",
            "category", "confidence", "scan_status",
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "file_id": row["id"],
                "sha256": row["sha256"],
                "path": row["path"],
                "size_bytes": row["size_bytes"],
                "mime_type": row["mime_type"] or "",
                "category": row["category_name"] or "",
                "confidence": row["cat_confidence"] or "",
                "scan_status": row["scan_status"],
            })
    return out_file
