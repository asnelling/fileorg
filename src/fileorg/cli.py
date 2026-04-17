from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

app = typer.Typer(help="fileorg — local-first file categorization tool", no_args_is_help=True)
console = Console()

_DEFAULT_DB = Path("data/fileorg.db")
_DEFAULT_DEST = Path("fileorg-output")
_DEFAULT_MODEL = "llama3.2"


@app.command()
def scan(
    source: Path = typer.Option(..., "--source", "-s", help="Directory to scan", exists=True, file_okay=False),
    dest: Path = typer.Option(_DEFAULT_DEST, "--dest", "-d", help="Output directory for exports"),
    db: Path = typer.Option(_DEFAULT_DB, "--db", help="Path to SQLite database"),
    model: str = typer.Option(_DEFAULT_MODEL, "--model", help="Ollama model name"),
    plugins: Optional[str] = typer.Option(None, "--plugins", help="Comma-separated plugin names (default: all)"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume previous scan"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip AI categorization"),
    follow_symlinks: bool = typer.Option(False, "--follow-symlinks", help="Follow symlinks"),
) -> None:
    """Scan a directory and categorize files."""
    from fileorg.scanner.pipeline import run_scan, ScanProgress
    from fileorg.ai.client import OllamaClient
    import time

    enabled_plugins = [p.strip() for p in plugins.split(",")] if plugins else None

    if not dry_run:
        client = OllamaClient(model=model)
        if not client.is_available():
            console.print(f"[yellow]Warning:[/yellow] Ollama model '{model}' not available. Use --dry-run to skip AI, or ensure Ollama is running.")

    db.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning...", total=None)

        def on_progress(p: ScanProgress) -> None:
            progress.update(task, total=p.total or 1, completed=p.processed,
                            description=f"[cyan]{Path(p.current_file).name[:40]}[/cyan]")

        result = run_scan(
            source_dir=source,
            db_path=db,
            model=model,
            enabled_plugins=enabled_plugins,
            resume=resume,
            dry_run=dry_run,
            follow_symlinks=follow_symlinks,
            progress_callback=on_progress,
        )

    elapsed = time.time() - start
    console.print(f"\n[green]Scan complete[/green] in {elapsed:.0f}s")

    from fileorg.db.connection import get_connection
    from fileorg.db import queries as q
    conn = get_connection(db)
    stats = q.get_overview_stats(conn)
    conn.close()

    table = Table(show_header=False, box=None)
    table.add_row("Files scanned", str(stats["total_files"]))
    table.add_row("Categorized", f"{stats['categorized_count']} ({stats['categorized_pct']}%)")
    table.add_row("Errors", str(stats["error_count"]))
    table.add_row("Categories found", str(stats["category_count"]))
    table.add_row("Clueless flagged", str(stats["clueless_count"]))
    console.print(table)


@app.command()
def dashboard(
    db: Path = typer.Option(_DEFAULT_DB, "--db", help="Path to SQLite database"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind"),
    port: int = typer.Option(8000, "--port", help="Port to listen on"),
) -> None:
    """Start the web dashboard."""
    import uvicorn
    from fileorg.dashboard.app import create_app

    if not db.exists():
        console.print(f"[red]Database not found:[/red] {db}\nRun [bold]fileorg scan[/bold] first.")
        raise typer.Exit(1)

    console.print(f"Dashboard at [link]http://{host}:{port}[/link] — Ctrl+C to stop")
    uvicorn.run(create_app(db), host=host, port=port)


@app.command()
def status(
    db: Path = typer.Option(_DEFAULT_DB, "--db", help="Path to SQLite database"),
) -> None:
    """Show scan status summary."""
    if not db.exists():
        console.print(f"[yellow]No database at {db}.[/yellow] Run [bold]fileorg scan[/bold] first.")
        raise typer.Exit(1)

    from fileorg.db.connection import get_connection
    from fileorg.db import queries as q

    conn = get_connection(db)
    stats = q.get_overview_stats(conn)
    run = q.get_last_scan_run(conn)
    enc_rows = q.list_encrypted_volumes(conn)
    keys_found = sum(1 for r in enc_rows if r["key_discovered"])
    conn.close()

    table = Table(title="fileorg status", show_header=False)
    if run:
        table.add_row("Last scan", f"{run['started_at'][:19].replace('T',' ')}  ({run['status']})")
        table.add_row("Source", run["source_dir"])
    table.add_row("Total files", f"{stats['total_files']:,}")
    table.add_row("Categorized", f"{stats['categorized_count']:,} ({stats['categorized_pct']}%)")
    table.add_row("Errors", str(stats["error_count"]))
    table.add_row("Pending", str(stats["pending_count"]))
    table.add_row("Categories", str(stats["category_count"]))
    table.add_row("Encrypted", f"{stats['encrypted_count']}  ({keys_found} keys found)")
    table.add_row("Clueless", str(stats["clueless_count"]))
    console.print(table)


@app.command()
def export(
    dest: Path = typer.Option(..., "--dest", help="Output directory"),
    db: Path = typer.Option(_DEFAULT_DB, "--db", help="Path to SQLite database"),
    format: str = typer.Option("symlinks", "--format", help="Output format: symlinks, json, csv"),
    category: Optional[str] = typer.Option(None, "--category", help="Filter to category subtree"),
) -> None:
    """Export categorized files as symlinks, JSON, or CSV."""
    from fileorg.export.exporter import run_export

    if not db.exists():
        console.print(f"[red]Database not found:[/red] {db}")
        raise typer.Exit(1)

    console.print(f"Exporting ({format}) to {dest}...")
    out = run_export(db, dest, format=format, category_filter=category)
    console.print(f"[green]Done:[/green] {out}")


@app.command()
def check() -> None:
    """Check local dependencies and report their versions."""
    import importlib.metadata
    import sys
    from rich.text import Text

    table = Table(title="fileorg dependency check")
    table.add_column("Dependency", style="bold")
    table.add_column("Status")
    table.add_column("Version / Detail")

    all_ok = True

    def _badge(status: str) -> Text:
        colours = {"ok": "green", "not installed": "red", "not running": "yellow", "no models": "yellow"}
        return Text(status, style=f"bold {colours.get(status, 'white')}")

    def _pkg(name: str, display: str | None = None) -> tuple[str, str]:
        try:
            v = importlib.metadata.version(name)
            return "ok", v
        except importlib.metadata.PackageNotFoundError:
            return "not installed", ""

    # Python
    table.add_row("Python", _badge("ok"), sys.version.split()[0])

    # ollama package
    status, ver = _pkg("ollama")
    if status != "ok":
        all_ok = False
    table.add_row("ollama (package)", _badge(status), ver or "pip install ollama")

    # Ollama daemon + models
    daemon_status, daemon_detail, model_lines = "not running", "https://ollama.com", []
    try:
        import ollama as _ol
        result = _ol.list()
        models = result.get("models", [])
        if models:
            daemon_status = "ok"
            daemon_detail = "running"
            for m in models:
                name = m.get("model") or m.get("name", "?")
                size_gb = m.get("size", 0) / 1_073_741_824
                model_lines.append(f"{name} ({size_gb:.1f} GB)")
        else:
            daemon_status = "no models"
            daemon_detail = "run: ollama pull llama3.2"
    except Exception:
        pass

    table.add_row("Ollama daemon", _badge(daemon_status), daemon_detail)

    if model_lines:
        first, *rest = model_lines
        table.add_row("Ollama models", _badge("ok"), first)
        for line in rest:
            table.add_row("", Text(""), line)
    elif daemon_status == "no models":
        table.add_row("Ollama models", _badge("no models"), "run: ollama pull llama3.2")
    else:
        table.add_row("Ollama models", _badge("not running"), "—")

    # python-magic package
    status, ver = _pkg("python-magic")
    if status != "ok":
        all_ok = False
    table.add_row("python-magic", _badge(status), ver or "pip install python-magic")

    # libmagic system library
    try:
        import magic as _magic
        _magic.Magic()
        table.add_row("libmagic (system)", _badge("ok"), "available")
    except Exception:
        all_ok = False
        table.add_row("libmagic (system)", _badge("not installed"), "apt install libmagic1")

    # Pillow
    status, ver = _pkg("Pillow")
    if status != "ok":
        all_ok = False
    table.add_row("Pillow", _badge(status), ver or "pip install Pillow")

    # piexif
    status, ver = _pkg("piexif")
    if status != "ok":
        all_ok = False
    table.add_row("piexif", _badge(status), ver or "pip install piexif")

    # pytesseract package
    status, ver = _pkg("pytesseract")
    if status != "ok":
        all_ok = False
    table.add_row("pytesseract (package)", _badge(status), ver or "pip install pytesseract")

    # tesseract binary
    try:
        import pytesseract as _tess
        tess_ver = str(_tess.get_tesseract_version())
        table.add_row("tesseract (binary)", _badge("ok"), tess_ver)
    except Exception:
        all_ok = False
        table.add_row("tesseract (binary)", _badge("not installed"), "apt install tesseract-ocr")

    # py7zr
    status, ver = _pkg("py7zr")
    if status != "ok":
        all_ok = False
    table.add_row("py7zr", _badge(status), ver or "pip install py7zr")

    console.print(table)

    if not all_ok:
        raise typer.Exit(1)


plugins_app = typer.Typer(help="Plugin management commands")
app.add_typer(plugins_app, name="plugins")


@plugins_app.command("list")
def plugins_list() -> None:
    """List all registered plugins."""
    from fileorg.plugins.registry import build_default_registry

    registry = build_default_registry()
    table = Table(title="Registered Plugins")
    table.add_column("Name", style="bold")
    table.add_column("Class")
    for plugin in registry.all():
        table.add_row(plugin.name, type(plugin).__name__)
    console.print(table)
