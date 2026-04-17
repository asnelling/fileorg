from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from fileorg.dashboard.app import templates
from fileorg.db.connection import get_connection
from fileorg.db import queries

router = APIRouter()


@router.get("/clueless", response_class=HTMLResponse)
async def clueless_list(request: Request) -> HTMLResponse:
    conn = get_connection(request.app.state.db_path)
    files = queries.list_clueless_files(conn, limit=200)
    conn.close()
    return templates.TemplateResponse("clueless.html", {
        "request": request,
        "files": [dict(f) for f in files],
    })
