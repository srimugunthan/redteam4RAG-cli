"""
redteam4rag/cli/report.py

Report subcommands — reformat existing JSON scan reports.
"""
from __future__ import annotations

import typer

app = typer.Typer(help="Report utilities.")


@app.command("reformat")
def reformat(
    input_path: str = typer.Argument(..., help="Path to existing JSON report"),
    output: str = typer.Option("report", "--output", "-o", help="Base output path"),
    format: str = typer.Option("md", "--format", "-f", help="md | html | all"),
):
    """Reformat an existing JSON report into md/html/all formats."""
    import json
    from pathlib import Path
    from redteam4rag.reports.builder import ReportBuilder
    from redteam4rag.models import (
        ScanResult,
        ScanMetadata,
        AttackResult,
        AttackStatus,
        Severity,
        JudgeVerdict,
    )

    data = json.loads(Path(input_path).read_text())

    meta = data.get("metadata", {})
    metadata = ScanMetadata(
        scan_id=meta.get("scan_id", ""),
        target_url=meta.get("target_url", ""),
        suite_name=meta.get("suite_name", ""),
        judge=meta.get("judge", ""),
        generator=meta.get("generator", ""),
        started_at=meta.get("started_at", ""),
        finished_at=meta.get("finished_at", ""),
        duration_seconds=meta.get("duration_seconds", 0.0),
        redteam4rag_version=meta.get("redteam4rag_version", "1.0.0"),
    )

    results = []
    for r in data.get("results", []):
        jv = r.get("judge_verdict")
        verdict = (
            JudgeVerdict(
                passed=jv["passed"],
                reasoning=jv.get("reasoning", ""),
                confidence=jv.get("confidence"),
                judge_name=jv.get("judge_name", ""),
            )
            if jv
            else None
        )
        results.append(
            AttackResult(
                id=r.get("id", ""),
                attack_name=r.get("attack_name", ""),
                category=r.get("category", ""),
                severity=Severity(r.get("severity", "info")),
                status=AttackStatus(r.get("status", "errored")),
                query=r.get("query", ""),
                retrieved_chunks=r.get("retrieved_chunks", []),
                response=r.get("response", ""),
                judge_verdict=verdict,
                evidence=r.get("evidence", {}),
                latency_ms=r.get("latency_ms", 0.0),
                error=r.get("error"),
            )
        )

    result = ScanResult(metadata=metadata, results=results)
    ReportBuilder().write(result, output, format)
    typer.echo(f"Report written to {output}")
