from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fileorg.db.connection import get_connection
from fileorg.db import queries
from fileorg.plugins.clueless import CluelessPlugin
from fileorg.plugins.registry import build_default_registry
from fileorg.scanner.hasher import sha256_file
from fileorg.scanner.walker import walk


def _detect_mime(path: Path) -> str | None:
    try:
        import magic
        return magic.from_file(str(path), mime=True)
    except Exception:
        return mimetypes.guess_type(str(path))[0]


@dataclass
class ScanProgress:
    run_id: int
    total: int
    processed: int
    current_file: str
    status: str


def run_scan(
    source_dir: Path,
    db_path: Path,
    model: str = "llama3.2",
    enabled_plugins: list[str] | None = None,
    resume: bool = True,
    dry_run: bool = False,
    follow_symlinks: bool = False,
    progress_callback: Callable[[ScanProgress], None] | None = None,
) -> ScanProgress:
    conn = get_connection(db_path)
    run_id = queries.create_scan_run(conn, str(source_dir))
    conn.commit()

    known: dict[str, str] = queries.get_all_file_statuses(conn) if resume else {}

    total = sum(1 for _ in walk(source_dir, follow_symlinks, skip_path=db_path))
    queries.update_scan_run_total(conn, run_id, total)
    conn.commit()

    registry = build_default_registry(enabled_plugins)
    clueless_plugin = CluelessPlugin()

    categorizer = None
    if not dry_run:
        from fileorg.scanner.categorizer import OllamaCategorizer
        categorizer = OllamaCategorizer(model=model)

    processed = 0
    for path in walk(source_dir, follow_symlinks, skip_path=db_path):
        current_file = str(path)
        try:
            stat = path.stat()
            sha256 = sha256_file(path)

            if resume and known.get(sha256) == "categorized":
                queries.upsert_file(conn, sha256, str(path), run_id, stat.st_size)
                conn.commit()
                processed += 1
                if progress_callback:
                    progress_callback(ScanProgress(run_id, total, processed, current_file, "running"))
                continue

            file_id = queries.upsert_file(conn, sha256, str(path), run_id, stat.st_size)

            prior_status = known.get(sha256, "new")

            if prior_status not in ("clued",):
                mime_type = _detect_mime(path)
                queries.update_file_mime(conn, file_id, mime_type or "")
                queries.update_file_status(conn, file_id, "pending")

                for plugin in registry.all():
                    if plugin.accepts(path, mime_type):
                        clues = list(plugin.extract(path))
                        encrypted_type = next(
                            (c.value for c in clues if c.key == "_encrypted_volume_type"), None
                        )
                        clues = [c for c in clues if c.key != "_encrypted_volume_type"]
                        if encrypted_type:
                            queries.upsert_encrypted_volume(conn, file_id, encrypted_type)
                        queries.insert_clues(conn, file_id, plugin.name, [
                            {"key": c.key, "value": c.value, "confidence": c.confidence}
                            for c in clues
                        ])

                queries.update_file_status(conn, file_id, "clued")
            else:
                mime_row = conn.execute("SELECT mime_type FROM files WHERE id=?", (file_id,)).fetchone()
                mime_type = mime_row["mime_type"] if mime_row else None

            all_clues = queries.get_clues_for_file(conn, file_id)
            score, flagged, extra_clues = clueless_plugin.compute(file_id, all_clues, mime_type)
            queries.upsert_coverage(
                conn, file_id,
                plugin_count=len({r["plugin_name"] for r in all_clues if r["plugin_name"] != "clueless"}),
                total_confidence=sum(r["confidence"] for r in all_clues if r["plugin_name"] != "clueless"),
                clue_count=len([r for r in all_clues if r["plugin_name"] != "clueless"]),
                coverage_score=score,
                flagged=flagged,
            )
            queries.insert_clues(conn, file_id, "clueless", [
                {"key": c.key, "value": c.value, "confidence": c.confidence}
                for c in extra_clues
            ])

            if not dry_run and categorizer is not None:
                all_clues_for_ai = queries.get_clues_for_file(conn, file_id)
                result = categorizer.categorize(path, mime_type, list(all_clues_for_ai))
                category_id = queries.get_or_create_category(conn, result["category"])
                queries.upsert_file_category(conn, file_id, category_id, result["confidence"], model)
                queries.update_file_status(conn, file_id, "categorized")
            elif dry_run:
                queries.update_file_status(conn, file_id, "categorized")

        except Exception as e:
            try:
                file_id_for_err = conn.execute(
                    "SELECT id FROM files WHERE path=?", (current_file,)
                ).fetchone()
                if file_id_for_err:
                    queries.update_file_status(conn, file_id_for_err["id"], "error", str(e)[:500])
            except Exception:
                pass

        conn.commit()
        processed += 1
        if progress_callback:
            progress_callback(ScanProgress(run_id, total, processed, current_file, "running"))

    queries.finish_scan_run(conn, run_id, "completed", processed)
    conn.commit()
    conn.close()

    return ScanProgress(run_id, total, processed, "", "completed")
