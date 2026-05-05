"""
redteam4rag/cli/scan.py

The `scan` command — single entry-point for running a red-team scan.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import typer

from redteam4rag.models import AttackStatus

_SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _exceeds_fail_threshold(results, fail_on: str) -> bool:
    threshold = _SEVERITY_ORDER.get(fail_on.lower(), 3)
    for r in results:
        if r.status == AttackStatus.FAILED:
            if _SEVERITY_ORDER.get(r.severity.value, 0) >= threshold:
                return True
    return False


def scan(
    target: str = typer.Option("", "--target", "-t", help="URL of the RAG endpoint"),
    attacks_config: str = typer.Option("quick", "--attacks-config", help="Built-in name or YAML path"),
    judge: Optional[str] = typer.Option(None, "--judge", help="Override judge spec (e.g. regex, llm:claude-sonnet-4-6)"),
    judge_provider: str = typer.Option("anthropic", "--judge-provider", help="Judge LLM provider"),
    judge_model: str = typer.Option("claude-sonnet-4-6", "--judge-model", help="Judge LLM model"),
    generator_provider: str = typer.Option("anthropic", "--generator-provider", help="Generator LLM provider"),
    generator_model: str = typer.Option("claude-haiku-4-5-20251001", "--generator-model", help="Generator LLM model"),
    output: str = typer.Option("report", "--output", "-o", help="Base output path"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json/md/html/all"),
    concurrency: int = typer.Option(5, "--concurrency", help="Max concurrent attacks"),
    retry: int = typer.Option(2, "--retry", help="Retry count on transient errors"),
    mutation_strategy: str = typer.Option("static", "--mutation-strategy", help="Mutation strategy: static/llm/template"),
    mutation_count: int = typer.Option(0, "--mutation-count", help="Number of mutation variants"),
    include_trace: bool = typer.Option(False, "--include-trace", help="Include LLM trace in output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run in dry-run mode (no real probes)"),
    fail_on: str = typer.Option("high", "--fail-on", help="Severity threshold for exit 1: info/low/medium/high/critical"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
):
    """Run a red-team scan against a RAG endpoint."""
    from redteam4rag.core.config import ScanConfig
    from redteam4rag.core.attack_config_loader import AttackConfigLoader, ConfigError
    from redteam4rag.adapters.http import HTTPAdapter
    from redteam4rag.engine.orchestrator import Orchestrator
    from redteam4rag.reports.builder import ReportBuilder

    # 1. Validate target
    if not target and not dry_run:
        typer.echo("Error: --target is required unless --dry-run is set.", err=True)
        raise typer.Exit(code=2)

    # 2. Load AttackConfig
    try:
        attack_config = AttackConfigLoader.load(attacks_config)
    except ConfigError as e:
        typer.echo(f"Error loading attack config: {e}", err=True)
        raise typer.Exit(code=2)

    # 3. Build ScanConfig
    config_kwargs = dict(
        target_url=target,
        attacks_config=attacks_config,
        judge_provider=judge_provider,
        judge_model=judge_model,
        generator_provider=generator_provider,
        generator_model=generator_model,
        output_path=output,
        output_format=format,
        concurrency=concurrency,
        retry=retry,
        mutation_strategy=mutation_strategy,
        mutation_count=mutation_count,
        include_trace=include_trace,
        dry_run=dry_run,
        fail_on=fail_on,
        verbose=verbose,
    )
    # Apply judge override to attack_config if supplied
    if judge is not None:
        attack_config = type(attack_config)(
            name=attack_config.name,
            generator=attack_config.generator,
            judge=judge,
            concurrency=attack_config.concurrency,
            attacks=attack_config.attacks,
        )

    config = ScanConfig(**config_kwargs)

    # 4. Validate openai_api_key when judge_provider is openai
    if judge_provider.lower() == "openai" and config.openai_api_key is None:
        typer.echo(
            "Error: --judge-provider=openai requires the OPENAI_API_KEY environment variable to be set.",
            err=True,
        )
        raise typer.Exit(code=2)

    # 5. Build adapter and orchestrator
    adapter = HTTPAdapter(config)
    orchestrator = Orchestrator(config, attack_config, adapter, forced_judge_spec=judge)

    # 6. Run
    result = asyncio.run(orchestrator.run())

    # 7. Write report
    ReportBuilder().write(result, output, format)

    # 8. Dry-run short-circuit
    if dry_run:
        typer.echo("Dry run complete")
        raise typer.Exit(code=0)

    # 9. Check fail_on threshold
    if _exceeds_fail_threshold(result.results, fail_on):
        summary = result.summary
        typer.echo(
            f"FAILED: {summary.failed} attack(s) exceeded severity threshold '{fail_on}'. "
            f"Total: {summary.total}, Passed: {summary.passed}, "
            f"Failed: {summary.failed}, Errored: {summary.errored}"
        )
        raise typer.Exit(code=1)

    # 10. Print summary and exit 0
    summary = result.summary
    typer.echo(
        f"Scan complete. Total: {summary.total}, Passed: {summary.passed}, "
        f"Failed: {summary.failed}, Errored: {summary.errored}"
    )
