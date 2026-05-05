"""
tests/integration/test_orchestrator.py

Integration tests for the Orchestrator. Require --live-rag flag.

All tests in this module use the live_rag_server fixture and are skipped
unless pytest is invoked with --live-rag.
"""

from __future__ import annotations

import asyncio

import pytest

from redteam4rag.core.config import ScanConfig
from redteam4rag.core.attack_config_loader import AttackConfigLoader
from redteam4rag.adapters.http import HTTPAdapter
from redteam4rag.engine.orchestrator import Orchestrator
from redteam4rag.models import ScanResult, AttackStatus, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(live_rag_server: str, **overrides) -> ScanConfig:
    """Build a ScanConfig pointing at the live test server."""
    defaults = {
        "target_url": f"{live_rag_server}/query",
        "attacks_config": "quick",
        "anthropic_api_key": "sk-test-key",
        "concurrency": 3,
        "mutation_count": 0,
        "mutation_strategy": "static",
        "dry_run": False,
        "retry": 0,
        "timeout_seconds": 10.0,
    }
    defaults.update(overrides)
    return ScanConfig(**defaults)


def _run_orchestrator(live_rag_server: str, **config_overrides) -> ScanResult:
    """Convenience: build config + adapter + orchestrator and run synchronously."""
    config = _make_config(live_rag_server, **config_overrides)
    attack_config = AttackConfigLoader.load(config.attacks_config)
    adapter = HTTPAdapter(config)
    orch = Orchestrator(config, attack_config, adapter)
    return asyncio.run(orch.run())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOrchestratorQuickScan:
    """Smoke tests using the 'quick' attack suite (12 attacks, 1 probe each)."""

    def test_quick_scan_returns_12_results(self, live_rag_server):
        """Each attack in the quick suite produces exactly one AttackResult."""
        result = _run_orchestrator(live_rag_server)
        assert isinstance(result, ScanResult)
        assert len(result.results) == 12

    def test_all_results_have_valid_status(self, live_rag_server):
        """Every result has a status that is one of the AttackStatus enum values."""
        result = _run_orchestrator(live_rag_server)
        valid_statuses = {s for s in AttackStatus}
        for r in result.results:
            assert r.status in valid_statuses, (
                f"Result {r.attack_name!r} has invalid status: {r.status!r}"
            )

    def test_all_results_have_attack_name_and_query(self, live_rag_server):
        """Every result has a non-empty attack_name and query."""
        result = _run_orchestrator(live_rag_server)
        for r in result.results:
            assert r.attack_name, f"Expected non-empty attack_name, got {r.attack_name!r}"
            assert r.query, f"Expected non-empty query for {r.attack_name!r}"

    def test_concurrency_1_completes(self, live_rag_server):
        """Concurrency=1 runs attacks sequentially without error."""
        result = _run_orchestrator(live_rag_server, concurrency=1)
        assert isinstance(result, ScanResult)
        assert len(result.results) == 12

    def test_concurrency_5_completes_without_deadlock(self, live_rag_server):
        """Concurrency=5 completes all 12 attacks (no deadlock or hang)."""
        result = _run_orchestrator(live_rag_server, concurrency=5)
        assert isinstance(result, ScanResult)
        assert len(result.results) == 12

    def test_dry_run_makes_zero_query_calls(self, live_rag_server):
        """In dry-run mode, the orchestrator returns an empty ScanResult immediately."""
        result = _run_orchestrator(live_rag_server, dry_run=True)
        assert isinstance(result, ScanResult)
        # Dry-run: no attacks executed → empty results list
        assert len(result.results) == 0

    def test_scan_metadata_populated(self, live_rag_server):
        """ScanMetadata fields are set correctly from the config."""
        result = _run_orchestrator(live_rag_server)
        meta = result.metadata
        assert meta.target_url == f"{live_rag_server}/query"
        assert meta.suite_name == "quick"
        assert meta.scan_id  # non-empty UUID string
        assert meta.started_at  # ISO-8601 timestamp
        assert meta.finished_at  # ISO-8601 timestamp
        assert meta.duration_seconds >= 0.0

    def test_static_strategy_exhausted_immediately(self, live_rag_server):
        """
        With mutation_strategy='static' and mutation_count=1,
        StaticStrategy.next_candidates() always returns [] so no mutations occur.
        Each attack still produces exactly one result.
        """
        result = _run_orchestrator(
            live_rag_server,
            mutation_strategy="static",
            mutation_count=1,
        )
        assert isinstance(result, ScanResult)
        # No extra results from mutations — still one result per attack
        assert len(result.results) == 12

    def test_summary_counts_match_results(self, live_rag_server):
        """ScanResult.summary totals are consistent with the results list."""
        result = _run_orchestrator(live_rag_server)
        summary = result.summary
        assert summary.total == len(result.results)
        assert summary.passed + summary.failed + summary.errored == summary.total

    def test_errored_results_have_status_errored(self, live_rag_server):
        """
        If any result has status ERRORED, it should have a non-None error field.
        (The test server is well-behaved, so we expect zero errored results,
        but this verifies the invariant holds regardless.)
        """
        result = _run_orchestrator(live_rag_server)
        for r in result.results:
            if r.status == AttackStatus.ERRORED:
                assert r.error is not None, (
                    f"ERRORED result {r.attack_name!r} should have a non-None error"
                )
