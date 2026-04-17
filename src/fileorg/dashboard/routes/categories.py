from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from fileorg.dashboard.app import templates
from fileorg.db.connection import get_connection
from fileorg.db import queries

router = APIRouter()


def _build_tree(categories: list) -> dict:
    tree: dict = {}
    for cat in categories:
        parts = cat["name"].split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {"_children": {}, "_data": None})["_children"]
        node[parts[-1]] = {"_children": {}, "_data": dict(cat)}
    return tree


@router.get("/categories", response_class=HTMLResponse)
async def categories_list(request: Request) -> HTMLResponse:
    conn = get_connection(request.app.state.db_path)
    cats = queries.list_categories(conn)
    conn.close()
    tree = _build_tree(cats)
    return templates.TemplateResponse("categories.html", {"request": request, "tree": tree, "categories": [dict(c) for c in cats]})


@router.get("/categories/{name:path}", response_class=HTMLResponse)
async def category_detail(request: Request, name: str) -> HTMLResponse:
    conn = get_connection(request.app.state.db_path)
    cats = queries.list_categories(conn)
    file_rows = queries.list_files(conn, category=name, limit=100)
    conn.close()
    return templates.TemplateResponse("categories.html", {
        "request": request,
        "tree": _build_tree(cats),
        "categories": [dict(c) for c in cats],
        "filtered_category": name,
        "files": [dict(f) for f in file_rows],
    })
