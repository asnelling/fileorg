from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from fileorg.dashboard.app import templates
from fileorg.db.connection import get_connection
from fileorg.db import queries

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def overview(request: Request) -> HTMLResponse:
    conn = get_connection(request.app.state.db_path)
    stats = queries.get_overview_stats(conn)
    conn.close()
    return templates.TemplateResponse("overview.html", {"request": request, "stats": stats})
