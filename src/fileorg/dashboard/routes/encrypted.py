from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from fileorg.dashboard.app import templates
from fileorg.db.connection import get_connection
from fileorg.db import queries

router = APIRouter()


@router.get("/encrypted", response_class=HTMLResponse)
async def encrypted_list(request: Request) -> HTMLResponse:
    conn = get_connection(request.app.state.db_path)
    volumes = queries.list_encrypted_volumes(conn)
    conn.close()
    return templates.TemplateResponse("encrypted.html", {
        "request": request,
        "volumes": [dict(v) for v in volumes],
    })
