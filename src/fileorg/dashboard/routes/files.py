from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from fileorg.dashboard.app import templates
from fileorg.db.connection import get_connection
from fileorg.db import queries

router = APIRouter()
PER_PAGE = 50


@router.get("/files", response_class=HTMLResponse)
async def files_list(
    request: Request,
    category: str = "",
    status: str = "",
    q: str = "",
    page: int = 1,
    sort: str = "size_desc",
) -> HTMLResponse:
    conn = get_connection(request.app.state.db_path)
    offset = (page - 1) * PER_PAGE
    rows = queries.list_files(
        conn,
        status=status or None,
        category=category or None,
        search=q or None,
        offset=offset,
        limit=PER_PAGE,
        sort=sort,
    )
    total = queries.count_files(conn, status=status or None)
    conn.close()
    return templates.TemplateResponse("files.html", {
        "request": request,
        "files": [dict(f) for f in rows],
        "total": total,
        "page": page,
        "per_page": PER_PAGE,
        "pages": max(1, (total + PER_PAGE - 1) // PER_PAGE),
        "q": q,
        "status": status,
        "category": category,
        "sort": sort,
    })


@router.get("/files/{file_id}", response_class=HTMLResponse)
async def file_detail(request: Request, file_id: int) -> HTMLResponse:
    conn = get_connection(request.app.state.db_path)
    file_row = queries.get_file_by_id(conn, file_id)
    if file_row is None:
        conn.close()
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
    clues = queries.get_clues_for_file(conn, file_id)
    cats = queries.get_categories_for_file(conn, file_id)
    conn.close()

    clues_by_plugin: dict[str, list[dict]] = {}
    for c in clues:
        clues_by_plugin.setdefault(c["plugin_name"], []).append(dict(c))

    return templates.TemplateResponse("clues.html", {
        "request": request,
        "file": dict(file_row),
        "clues_by_plugin": clues_by_plugin,
        "categories": [dict(c) for c in cats],
    })
