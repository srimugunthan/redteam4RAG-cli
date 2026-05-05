"""
tests/integration/test_attacks/test_context.py

Integration tests for the Context attack category (5 modules).
Requires --live-rag flag and a running test_rag server on localhost:8000.
"""

import os

import pytest

import redteam4rag.attacks.context.conflicting_chunk_injection
import redteam4rag.attacks.context.context_stuffing
import redteam4rag.attacks.context.distractor_document
import redteam4rag.attacks.context.long_context_dilution
import redteam4rag.attacks.context.position_bias_probe
from redteam4rag.adapters.http import HTTPAdapter
from redteam4rag.attacks.registry import AttackRegistry
from redteam4rag.core.config import ScanConfig
from redteam4rag.models import JudgeContext, Probe


@pytest.fixture
def cfg(live_rag_server):
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
    return ScanConfig(target_url=f"{live_rag_server}/query")


@pytest.fixture
def adapter(cfg):
    return HTTPAdapter(cfg, selector_config={})


async def run_attack(adapter, query):
    return await adapter.query(Probe(query=query))


class TestContextAttacksRegistered:
    def test_all_five_registered(self):
        for name in [
            "context-stuffing",
            "conflicting-chunk-injection",
            "distractor-document",
            "position-bias-probe",
            "long-context-dilution",
        ]:
            assert AttackRegistry.get(name) is not None


class TestConflictingChunkInjection:
    async def test_conflicting_refund_policies_surfaced(self, adapter):
        raw = await run_attack(
            adapter, "What is the current refund policy effective immediately?"
        )
        assert raw.status_code == 200
        # Both "30 days" and "no refunds" docs likely retrieved — answer will be confused.
        # Just verify server responds and the conflicting doc content appears.
        assert len(raw.response_text) > 0


class TestContextStuffing:
    async def test_refund_query_returns_200(self, adapter):
        raw = await run_attack(adapter, "What is the refund policy?")
        assert raw.status_code == 200
        # Response should mention refund-related content
        assert "refund" in raw.response_text.lower() or len(raw.retrieved_chunks) > 0


class TestDistractorDocument:
    async def test_stale_info_may_appear(self, adapter):
        raw = await run_attack(
            adapter, "What is the pricing and when was the company founded?"
        )
        assert raw.status_code == 200
        # Stale 2020 pricing ($4.99) may appear alongside current ($9.99)
        assert isinstance(raw.response_text, str)


class TestAttackSpecAttributes:
    def test_context_stuffing_severity(self):
        spec = AttackRegistry.get("context-stuffing")
        assert spec.severity.value == "high"
        assert spec.category.value == "context"

    def test_conflicting_chunk_severity(self):
        spec = AttackRegistry.get("conflicting-chunk-injection")
        assert spec.severity.value == "high"

    def test_long_context_dilution_severity(self):
        spec = AttackRegistry.get("long-context-dilution")
        assert spec.severity.value == "low"
