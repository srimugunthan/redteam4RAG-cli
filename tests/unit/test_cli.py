"""
tests/unit/test_cli.py

CLI layer unit tests using typer.testing.CliRunner.
No live server required.
"""
from __future__ import annotations

from typer.testing import CliRunner

from redteam4rag.cli.main import app

runner = CliRunner()

_ANTHROPIC_ENV = {"ANTHROPIC_API_KEY": "sk-test"}


class TestVersionCommand:
    def test_version_exits_0(self):
        result = runner.invoke(app, ["version"], env=_ANTHROPIC_ENV)
        assert result.exit_code == 0

    def test_version_prints_something(self):
        result = runner.invoke(app, ["version"], env=_ANTHROPIC_ENV)
        assert result.output.strip() != ""


class TestScanCommand:
    def test_scan_no_target_exits_2(self):
        result = runner.invoke(app, ["scan"], env=_ANTHROPIC_ENV)
        assert result.exit_code == 2

    def test_scan_unknown_attacks_config_exits_2(self):
        result = runner.invoke(
            app,
            ["scan", "--target", "http://localhost:9999", "--attacks-config", "nonexistent-suite-xyz"],
            env=_ANTHROPIC_ENV,
        )
        assert result.exit_code == 2

    def test_scan_dry_run_exits_not_2(self, tmp_path):
        # dry-run hits health_check(), which will fail since no server.
        # We check that with --dry-run and a target the command does not fail
        # with a usage error (exit 2).
        result = runner.invoke(
            app,
            [
                "scan",
                "--target", "http://localhost:9999/query",
                "--attacks-config", "quick",
                "--dry-run",
            ],
            env=_ANTHROPIC_ENV,
        )
        # Exit code is not 2 (usage error) — may be 0 or 1 depending on health_check
        assert result.exit_code != 2

    def test_scan_openai_judge_without_key_exits_2(self):
        result = runner.invoke(
            app,
            [
                "scan",
                "--target", "http://localhost:9999",
                "--judge-provider", "openai",
            ],
            env={"ANTHROPIC_API_KEY": "sk-test"},
        )
        assert result.exit_code == 2

    def test_scan_verbose_flag_accepted(self):
        # Verify --verbose is a recognised flag (--help exits 0 without running scan)
        result = runner.invoke(app, ["scan", "--verbose", "--help"], env=_ANTHROPIC_ENV)
        assert result.exit_code == 0


class TestPluginListCommand:
    def test_plugin_list_exits_0(self):
        result = runner.invoke(app, ["plugin", "list"], env=_ANTHROPIC_ENV)
        assert result.exit_code == 0

    def test_plugin_list_shows_24_attacks(self):
        result = runner.invoke(app, ["plugin", "list"], env=_ANTHROPIC_ENV)
        assert result.exit_code == 0
        # Should show 24 registered attacks in the table title
        assert "24" in result.output


class TestOutputAndFormatFlags:
    def test_output_format_all_flag_accepted(self):
        result = runner.invoke(app, ["scan", "--format", "all", "--help"], env=_ANTHROPIC_ENV)
        assert result.exit_code == 0

    def test_mutation_strategy_flag_accepted(self):
        result = runner.invoke(app, ["scan", "--mutation-strategy", "llm", "--help"], env=_ANTHROPIC_ENV)
        assert result.exit_code == 0

    def test_mutation_count_zero_accepted(self):
        result = runner.invoke(app, ["scan", "--mutation-count", "0", "--help"], env=_ANTHROPIC_ENV)
        assert result.exit_code == 0
