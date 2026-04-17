from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_PKG_DIR = Path(__file__).parent
STATIC_DIR = _PKG_DIR / "static"
TEMPLATES_DIR = _PKG_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app(db_path: Path) -> FastAPI:
    from fileorg.dashboard.routes import overview, categories, files, encrypted, clueless, api

    app = FastAPI(title="fileorg Dashboard")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.db_path = db_path

    app.include_router(overview.router)
    app.include_router(categories.router)
    app.include_router(files.router)
    app.include_router(encrypted.router)
    app.include_router(clueless.router)
    app.include_router(api.router)

    return app
