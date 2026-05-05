"""
redteam4rag/cli/main.py

Main Typer application — registers all sub-commands and sub-apps.
"""
from __future__ import annotations

import typer

from redteam4rag.cli import corpus, plugin, report
from redteam4rag.cli.scan import scan as _scan_fn

app = typer.Typer(name="redteam4rag", help="Automated red-teaming CLI for RAG systems.")

# Register the flat `scan` command
app.command("scan")(_scan_fn)

# Register sub-apps
app.add_typer(corpus.app, name="corpus")
app.add_typer(plugin.app, name="plugin")
app.add_typer(report.app, name="report")


@app.command()
def version():
    """Print the installed version."""
    import importlib.metadata

    try:
        ver = importlib.metadata.version("redteam4rag")
    except importlib.metadata.PackageNotFoundError:
        ver = "1.0.0"
    typer.echo(ver)
