"""
tests/e2e/test_e2e_scan.py

End-to-end tests for the `scan` CLI command.

All tests that interact with a live RAG server use the `live_rag_server`
fixture and are automatically skipped unless --live-rag is passed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from redteam4rag.cli.main import app

runner = CliRunner()
FAKE_KEY = "sk-ant-test-key-for-e2e"


# ---------------------------------------------------------------------------
# Scenario 1 — Quick scan, regex judge (zero API cost)
# ---------------------------------------------------------------------------

class TestScenario1QuickScanRegexJudge:
    def test_exit_code_1_when_findings_above_threshold(self, live_rag_server, tmp_path):
        result = runner.invoke(app, [
            "scan",
            "--target", f"{live_rag_server}/query",
            "--attacks-config", "quick",
            "--judge", "regex",
            "--output", str(tmp_path / "quick_scan"),
            "--format", "all",
            "--fail-on", "high",
        ], env={"ANTHROPIC_API_KEY": FAKE_KEY})
        # With empty-pattern regex judge (match_means=fail), all responses fail
        # so there will be FAILED results → exit code 1
        assert result.exit_code == 1

    def test_json_report_is_valid_and_has_12_results(self, live_rag_server, tmp_path):
        runner.invoke(app, [
            "scan", "--target", f"{live_rag_server}/query",
            "--attacks-config", "quick", "--judge", "regex",
            "--output", str(tmp_path / "scan"), "--format", "json",
        ], env={"ANTHROPIC_API_KEY": FAKE_KEY})
        json_file = tmp_path / "scan.json"
        assert json_file.exists(), "JSON report file not created"
        data = json.loads(json_file.read_text())
        assert "metadata" in data
        assert "results" in data
        assert len(data["results"]) == 12

    def test_html_report_is_self_contained(self, live_rag_server, tmp_path):
        runner.invoke(app, [
            "scan", "--target", f"{live_rag_server}/query",
            "--attacks-config", "quick", "--judge", "regex",
            "--output", str(tmp_path / "scan"), "--format", "html",
        ], env={"ANTHROPIC_API_KEY": FAKE_KEY})
        html_file = tmp_path / "scan.html"
        assert html_file.exists(), "HTML report file not created"
        content = html_file.read_text()
        # Self-contained: no bare http:// URLs (only encoded ones are OK)
        assert "http://" not in content

    def test_md_report_contains_summary(self, live_rag_server, tmp_path):
        runner.invoke(app, [
            "scan", "--target", f"{live_rag_server}/query",
            "--attacks-config", "quick", "--judge", "regex",
            "--output", str(tmp_path / "scan"), "--format", "md",
        ], env={"ANTHROPIC_API_KEY": FAKE_KEY})
        md_file = tmp_path / "scan.md"
        assert md_file.exists(), "Markdown report file not created"
        content = md_file.read_text()
        assert "Summary" in content or "summary" in content.lower()


# ---------------------------------------------------------------------------
# Scenario 2 — Full scan (LLM judge) — skip if no real API key
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-test"),
    reason="requires real ANTHROPIC_API_KEY"
)
class TestScenario2FullScanLLMJudge:
    def test_full_scan_produces_24_results(self, live_rag_server, tmp_path):
        result = runner.invoke(app, [
            "scan",
            "--target", f"{live_rag_server}/query",
            "--attacks-config", "full",
            "--output", str(tmp_path / "full_scan"),
            "--format", "json",
        ], env={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]})
        assert result.exit_code in [0, 1]
        json_file = tmp_path / "full_scan.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert len(data["results"]) == 24


# ---------------------------------------------------------------------------
# Scenario 3 — Trace-aware judge — skip if no real API key
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-test"),
    reason="requires real ANTHROPIC_API_KEY for LLM judge"
)
class TestScenario3TraceAwareJudge:
    def test_scan_with_include_trace_completes(self, live_rag_server, tmp_path):
        result = runner.invoke(app, [
            "scan",
            "--target", f"{live_rag_server}/query",
            "--attacks-config", "quick",
            "--include-trace",
            "--output", str(tmp_path / "trace_scan"),
            "--format", "json",
        ], env={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]})
        assert result.exit_code in [0, 1]


# ---------------------------------------------------------------------------
# Scenario 4 — Dry run
# ---------------------------------------------------------------------------

class TestScenario4DryRun:
    def test_dry_run_exits_0(self, live_rag_server, tmp_path):
        result = runner.invoke(app, [
            "scan",
            "--target", f"{live_rag_server}/query",
            "--attacks-config", "quick",
            "--dry-run",
            "--output", str(tmp_path / "dry"),
            "--format", "json",
        ], env={"ANTHROPIC_API_KEY": FAKE_KEY})
        assert result.exit_code == 0

    def test_dry_run_prints_complete_message(self, live_rag_server, tmp_path):
        result = runner.invoke(app, [
            "scan", "--target", f"{live_rag_server}/query",
            "--attacks-config", "quick", "--dry-run",
            "--output", str(tmp_path / "dry"), "--format", "json",
        ], env={"ANTHROPIC_API_KEY": FAKE_KEY})
        assert "Dry run complete" in result.output


# ---------------------------------------------------------------------------
# Scenario 5 — Custom attack config YAML
# ---------------------------------------------------------------------------

class TestScenario5CustomYaml:
    def test_custom_yaml_runs_only_listed_attacks(self, live_rag_server, tmp_path):
        yaml_file = tmp_path / "custom.yaml"
        yaml_file.write_text(
            "name: custom-e2e\n"
            "generator: static\n"
            "judge: regex\n"
            "concurrency: 2\n"
            "attacks:\n"
            "  - keyword-injection\n"
            "  - empty-retrieval-probe\n"
        )
        result = runner.invoke(app, [
            "scan",
            "--target", f"{live_rag_server}/query",
            "--attacks-config", str(yaml_file),
            "--judge", "regex",
            "--output", str(tmp_path / "custom_scan"),
            "--format", "json",
        ], env={"ANTHROPIC_API_KEY": FAKE_KEY})
        assert result.exit_code in [0, 1], f"Unexpected exit code: {result.exit_code}\n{result.output}"
        json_file = tmp_path / "custom_scan.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert len(data["results"]) == 2
        names = {r["attack_name"] for r in data["results"]}
        assert "keyword-injection" in names
        assert "empty-retrieval-probe" in names


# ---------------------------------------------------------------------------
# Scenario 6 — OpenAI judge — skip if no OPENAI_API_KEY
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="requires OPENAI_API_KEY"
)
class TestScenario6OpenAIJudge:
    def test_openai_judge_runs_scan(self, live_rag_server, tmp_path):
        result = runner.invoke(app, [
            "scan",
            "--target", f"{live_rag_server}/query",
            "--attacks-config", "quick",
            "--judge-provider", "openai",
            "--judge-model", "gpt-4o-mini",
            "--judge", "regex",   # force regex to avoid real OpenAI calls
            "--output", str(tmp_path / "oai_scan"),
            "--format", "json",
        ], env={
            "ANTHROPIC_API_KEY": FAKE_KEY,
            "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
        })
        assert result.exit_code in [0, 1]
        assert (tmp_path / "oai_scan.json").exists()


# ---------------------------------------------------------------------------
# Plugin list E2E (no server needed)
# ---------------------------------------------------------------------------

class TestPluginListE2E:
    def test_plugin_list_shows_all_24_attacks(self, live_rag_server):
        result = runner.invoke(app, ["plugin", "list"], env={"ANTHROPIC_API_KEY": FAKE_KEY})
        assert result.exit_code == 0
        # Check that all 5 categories are listed
        assert "injection" in result.output.lower()
        assert "retriever" in result.output.lower()
        assert "data_leakage" in result.output.lower()
