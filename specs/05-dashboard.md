# Spec: Web Dashboard

## Purpose

A read-only local web dashboard for exploring scan results. Shows file counts, categories, coverage health, encrypted volumes, and under-covered files. Uses HTMX for live scan progress updates without a JavaScript framework or build step.

## Technology

- **FastAPI** for the web server
- **Jinja2** for HTML templating
- **HTMX** (`htmx.min.js` bundled locally) for partial page refresh
- **No external CSS framework** — a single `style.css` with minimal custom styles

## Files

### `src/fileorg/dashboard/app.py`

FastAPI application factory.

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="fileorg Dashboard")
    # Mount static files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    # Store db_path in app.state so routes can access it
    app.state.db_path = db_path
    # Include all routers
    app.include_router(overview_router)
    app.include_router(categories_router)
    app.include_router(files_router)
    app.include_router(encrypted_router)
    app.include_router(clueless_router)
    app.include_router(api_router)
    return app
```

The `STATIC_DIR` and `TEMPLATES_DIR` are paths relative to the `dashboard/` package directory.

### `src/fileorg/dashboard/routes/overview.py`

```python
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def overview(request: Request):
    conn = get_connection(request.app.state.db_path)
    stats = queries.get_overview_stats(conn)
    conn.close()
    return templates.TemplateResponse("overview.html", {"request": request, "stats": stats})
```

`get_overview_stats()` returns:
```python
{
    "total_files": int,
    "categorized_count": int,
    "categorized_pct": float,  # 0-100
    "error_count": int,
    "pending_count": int,
    "total_size_bytes": int,
    "category_count": int,
    "encrypted_count": int,
    "clueless_count": int,  # files with flagged_clueless=1
    "top_categories": [{"name": str, "file_count": int}, ...],  # top 8
    "recent_files": [{"path": str, "category": str, "confidence": float}, ...],  # last 10
    "last_scan": {"started_at": str, "status": str, "source_dir": str} | None,
}
```

### `src/fileorg/dashboard/routes/categories.py`

```python
@router.get("/categories", response_class=HTMLResponse)
async def categories(request: Request, parent: str = ""):
    # Returns all categories; if parent provided, filter to that subtree
    ...

@router.get("/categories/{name:path}", response_class=HTMLResponse)
async def category_detail(request: Request, name: str):
    # Shows files in a specific category with pagination
    ...
```

Category tree is built from flat `name` strings by splitting on `/` and nesting.

### `src/fileorg/dashboard/routes/files.py`

```python
@router.get("/files", response_class=HTMLResponse)
async def files(
    request: Request,
    category: str = "",
    status: str = "",
    q: str = "",
    page: int = 1,
    per_page: int = 50,
    sort: str = "size_desc",
):
    ...
```

Displays a paginated, searchable, filterable table of files. Search (`q`) matches against file path and clue values.

### `src/fileorg/dashboard/routes/clues.py`

```python
@router.get("/files/{file_id}", response_class=HTMLResponse)
async def file_detail(request: Request, file_id: int):
    # Shows per-file detail: metadata, all clues grouped by plugin, categories with confidence
    ...
```

### `src/fileorg/dashboard/routes/encrypted.py`

```python
@router.get("/encrypted", response_class=HTMLResponse)
async def encrypted(request: Request):
    # Shows encrypted_volumes table with volume type, key status, file path
    ...
```

### `src/fileorg/dashboard/routes/clueless.py`

```python
@router.get("/clueless", response_class=HTMLResponse)
async def clueless(request: Request):
    # Shows files ordered by coverage_score ASC
    # Includes plugin_count, clue_count, coverage_score, mime_type, suggested plugin
    ...
```

### `src/fileorg/dashboard/routes/api.py`

JSON API endpoints (no HTML, for HTMX polling and external consumers).

```python
@router.get("/api/status")
async def api_status(request: Request):
    """
    Returns current scan status for HTMX polling.
    {
        "scan_running": bool,
        "run_id": int | null,
        "processed": int,
        "total": int,
        "current_pct": float,
        "status": "running" | "completed" | "idle"
    }
    """

@router.get("/api/categories")
async def api_categories(request: Request):
    """Returns full category tree as nested JSON."""

@router.get("/api/export")
async def api_export(request: Request, format: str = "json", dest: str = ""):
    """Triggers export; returns {'status': 'ok', 'path': str}."""
```

## Templates

All templates extend `base.html`.

### `base.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>fileorg — {% block title %}Dashboard{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="/static/htmx.min.js"></script>
</head>
<body>
  <nav>
    <a href="/">Overview</a>
    <a href="/categories">Categories</a>
    <a href="/files">Files</a>
    <a href="/encrypted">Encrypted</a>
    <a href="/clueless">Clueless</a>
  </nav>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

### `overview.html`

Widgets (all in `<section>` blocks):
1. **Scan status bar** — shows last scan source dir, status badge (green=completed, yellow=running, red=interrupted), time. If running: `<div hx-get="/api/status" hx-trigger="every 2s" hx-swap="innerHTML">` to live-update a progress bar.
2. **Summary counts** — cards for: Total Files, Categorized (%), Errors, Categories, Encrypted, Clueless flagged
3. **Top categories** — ordered list of top 8 categories with file counts
4. **Recent files** — table of last 10 categorized files with path, category, confidence

### `categories.html`

- Hierarchical tree rendered from nested dicts
- Each category shows name, file count, total size
- Click to filter to `/files?category=<name>`

### `files.html`

- Search box: `<form method="get" action="/files">`
- Filter dropdowns: Status, Category
- Table columns: Path (truncated), Category, Confidence (badge), Size, MIME type
- Pagination: Previous / Next links
- Row links to `/files/{file_id}`

### `clues.html` (per-file detail)

- File metadata section: path, sha256 (truncated), size, MIME, scan status
- Clues section: grouped by plugin, each group shows plugin name as a header; clue rows show key, value, confidence bar
- Categories section: each category with confidence percentage bar and AI reasoning text

### `encrypted.html`

Table: File path | Volume type | Key discovered (badge) | Notes

### `clueless.html`

Table: File path | MIME | Plugin count | Coverage score (progress bar) | Suggested plugin

## Static Files

### `style.css`

Minimal CSS — no framework. Rules for:
- Body font, nav links, main padding
- `.card` — summary stat card
- `.badge` — colored status badge (green/yellow/red/gray)
- `.progress` — thin progress bar showing confidence
- `table` — clean table styles
- Responsive nav (collapses on narrow screens)

### `htmx.min.js`

Download HTMX 1.9.x minified JS and bundle it locally. No CDN dependency — consistent with "Local First" requirement.

## How to run the dashboard

```python
# cli.py dashboard command calls:
import uvicorn
app = create_app(db_path)
uvicorn.run(app, host=host, port=port)
```

## Testing

`tests/test_dashboard.py` using `httpx` async client:
- `TestClient(create_app(tmp_db_path))` — creates app with in-memory seeded DB
- Test each route returns 200
- Test `/api/status` returns expected JSON shape
- Test `/files?q=foo` filters correctly
- Test `/files/999` returns 404 for unknown file_id
