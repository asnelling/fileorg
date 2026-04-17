from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from fileorg.db.connection import get_connection
from fileorg.db import queries

router = APIRouter(prefix="/api")


@router.get("/status")
async def api_status(request: Request) -> JSONResponse:
    conn = get_connection(request.app.state.db_path)
    run = queries.get_last_scan_run(conn)
    conn.close()
    if run is None:
        return JSONResponse({"scan_running": False, "run_id": None, "processed": 0, "total": 0, "current_pct": 0.0, "status": "idle"})
    total = run["total_files"] or 0
    processed = run["processed"] or 0
    pct = round(100 * processed / total, 1) if total else 0.0
    return JSONResponse({
        "scan_running": run["status"] == "running",
        "run_id": run["id"],
        "processed": processed,
        "total": total,
        "current_pct": pct,
        "status": run["status"],
    })


@router.get("/categories")
async def api_categories(request: Request) -> JSONResponse:
    conn = get_connection(request.app.state.db_path)
    cats = queries.list_categories(conn)
    conn.close()
    return JSONResponse([dict(c) for c in cats])


@router.get("/export")
async def api_export(request: Request, format: str = "json", dest: str = "") -> JSONResponse:
    from pathlib import Path
    from fileorg.export.exporter import run_export
    db_path = request.app.state.db_path
    dest_path = Path(dest) if dest else Path("fileorg-output")
    try:
        out = run_export(db_path, dest_path, format=format)
        return JSONResponse({"status": "ok", "path": str(out)})
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
