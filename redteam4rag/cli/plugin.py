"""
redteam4rag/cli/plugin.py

Plugin subcommands — list registered attacks and judges.
"""
from __future__ import annotations

import typer

app = typer.Typer(help="List registered attacks and judges.")


@app.command("list")
def list_plugins():
    """List all registered attack modules and judge types."""
    from redteam4rag.core.attack_config_loader import AttackConfigLoader
    from redteam4rag.attacks.registry import AttackRegistry

    AttackConfigLoader._import_all_attacks()
    attacks = AttackRegistry.all()

    from rich.table import Table
    from rich.console import Console

    table = Table(title=f"Registered Attacks ({len(attacks)})")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Severity")
    table.add_column("Tags")
    for name, spec in sorted(attacks.items()):
        table.add_row(
            name,
            spec.category.value,
            spec.severity.value,
            ", ".join(sorted(spec.tags)),
        )
    Console().print(table)
