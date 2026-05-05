"""
redteam4rag/cli/corpus.py

Corpus subcommands — inspect/manage the target RAG corpus.
"""
from __future__ import annotations

import typer
import httpx

app = typer.Typer(help="Inspect and manage the target RAG corpus.")


@app.command("inspect")
def inspect(
    target: str = typer.Option(..., "--target", "-t", help="RAG base URL"),
):
    """List documents in the target RAG corpus."""
    resp = httpx.get(f"{target.rstrip('/')}/corpus")
    resp.raise_for_status()
    docs = resp.json()
    from rich.table import Table
    from rich.console import Console
    table = Table(title="Corpus Documents")
    table.add_column("doc_id")
    table.add_column("namespace")
    table.add_column("snippet")
    for doc in docs:
        table.add_row(
            doc.get("doc_id", ""),
            doc.get("namespace", ""),
            doc.get("text", "")[:60],
        )
    Console().print(table)
