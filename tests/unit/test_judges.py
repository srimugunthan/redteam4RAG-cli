"""
tests/unit/test_judges.py

Unit tests for the Phase 2C Judge Layer.
asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from redteam4rag.judges.base import BaseJudge
from redteam4rag.judges.compound import CompoundJudge
from redteam4rag.judges.llm import LLMJudge, _build_prompt
from redteam4rag.judges.regex import RegexJudge
from redteam4rag.judges.registry import JudgeRegistry
from redteam4rag.models import JudgeContext, JudgeVerdict, LLMTrace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(
    response: str = "some response",
    query: str = "test query",
    retrieved_chunks: list[str] | None = None,
    trace: LLMTrace | None = None,
) -> JudgeContext:
    return JudgeContext(
        query=query,
        retrieved_chunks=retrieved_chunks or ["chunk1"],
        response=response,
        attack_metadata={},
        trace=trace,
    )


def make_mock_provider(return_value: str) -> MagicMock:
    """Return a mock that satisfies the LLMProvider Protocol."""
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=return_value)
    return provider


def make_always_pass_judge() -> BaseJudge:
    """Create a judge that always returns PASS."""
    j = MagicMock(spec=BaseJudge)
    j.judge = AsyncMock(return_value=JudgeVerdict(passed=True, reasoning="always pass"))
    return j


def make_always_fail_judge() -> BaseJudge:
    """Create a judge that always returns FAIL."""
    j = MagicMock(spec=BaseJudge)
    j.judge = AsyncMock(return_value=JudgeVerdict(passed=False, reasoning="always fail"))
    return j


# ---------------------------------------------------------------------------
# RegexJudge tests
# ---------------------------------------------------------------------------

class TestRegexJudge:

    async def test_match_fail_mode_returns_false(self):
        """Pattern matches, match_means='fail' → passed=False"""
        judge = RegexJudge(pattern=r"secret", match_means="fail")
        ctx = make_ctx(response="this contains secret info")
        verdict = await judge.judge(ctx)
        assert verdict.passed is False
        assert verdict.reasoning == "Pattern matched"

    async def test_no_match_fail_mode_returns_true(self):
        """Pattern does not match, match_means='fail' → passed=True"""
        judge = RegexJudge(pattern=r"secret", match_means="fail")
        ctx = make_ctx(response="nothing suspicious here")
        verdict = await judge.judge(ctx)
        assert verdict.passed is True
        assert verdict.reasoning == "No pattern match"

    async def test_match_pass_mode_returns_true(self):
        """Pattern matches, match_means='pass' → passed=True"""
        judge = RegexJudge(pattern=r"allowed", match_means="pass")
        ctx = make_ctx(response="this is allowed content")
        verdict = await judge.judge(ctx)
        assert verdict.passed is True
        assert verdict.reasoning == "Pattern matched"

    async def test_no_match_pass_mode_returns_false(self):
        """Pattern does not match, match_means='pass' → passed=False"""
        judge = RegexJudge(pattern=r"allowed", match_means="pass")
        ctx = make_ctx(response="something completely different")
        verdict = await judge.judge(ctx)
        assert verdict.passed is False
        assert verdict.reasoning == "No pattern match"

    def test_invalid_pattern_raises(self):
        """Invalid regex pattern raises re.error at construction time."""
        with pytest.raises(re.error):
            RegexJudge(pattern=r"[invalid")


# ---------------------------------------------------------------------------
# LLMJudge tests
# ---------------------------------------------------------------------------

class TestLLMJudge:

    async def test_fail_response_returns_fail_verdict(self):
        """Provider returns 'FAIL ...' → JudgeVerdict(passed=False)"""
        provider = make_mock_provider("FAIL - the response leaks PII")
        judge = LLMJudge(provider=provider)
        ctx = make_ctx()
        verdict = await judge.judge(ctx)
        assert verdict.passed is False

    async def test_pass_response_returns_pass_verdict(self):
        """Provider returns 'PASS ...' → JudgeVerdict(passed=True)"""
        provider = make_mock_provider("PASS - no vulnerability")
        judge = LLMJudge(provider=provider)
        ctx = make_ctx()
        verdict = await judge.judge(ctx)
        assert verdict.passed is True

    async def test_garbled_response_fallback(self):
        """Provider returns text without PASS/FAIL → fallback verdict with confidence=None"""
        garbled = "I cannot determine whether this is safe or not, maybe yes maybe no"
        provider = make_mock_provider(garbled)
        judge = LLMJudge(provider=provider)
        ctx = make_ctx()
        verdict = await judge.judge(ctx)
        # Default to PASS (avoid false positives)
        assert verdict.passed is True
        assert verdict.confidence is None

    async def test_trace_assembled_prompt_included_in_prompt(self):
        """ctx.trace with assembled_prompt → the built prompt contains 'injected payload'"""
        provider = make_mock_provider("PASS")
        judge = LLMJudge(provider=provider)
        trace = LLMTrace(assembled_prompt="injected payload")
        ctx = make_ctx(trace=trace)
        await judge.judge(ctx)

        # Inspect the prompt actually sent to the provider
        call_args = provider.complete.call_args
        sent_prompt: str = call_args[0][0] if call_args[0] else call_args.kwargs["prompt"]
        assert "injected payload" in sent_prompt

    async def test_no_trace_excludes_execution_trace_section(self):
        """ctx.trace=None → prompt does NOT contain 'Execution Trace'"""
        provider = make_mock_provider("PASS")
        judge = LLMJudge(provider=provider)
        ctx = make_ctx(trace=None)
        await judge.judge(ctx)

        call_args = provider.complete.call_args
        sent_prompt: str = call_args[0][0] if call_args[0] else call_args.kwargs["prompt"]
        assert "Execution Trace" not in sent_prompt
        assert "assembled_prompt" not in sent_prompt

    async def test_trace_reasoning_steps_included_in_prompt(self):
        """ctx.trace with reasoning_steps → steps appear in the built prompt"""
        provider = make_mock_provider("PASS")
        judge = LLMJudge(provider=provider)
        trace = LLMTrace(reasoning_steps=["step1", "step2"])
        ctx = make_ctx(trace=trace)
        await judge.judge(ctx)

        call_args = provider.complete.call_args
        sent_prompt: str = call_args[0][0] if call_args[0] else call_args.kwargs["prompt"]
        assert "step1" in sent_prompt
        assert "step2" in sent_prompt


# ---------------------------------------------------------------------------
# CompoundJudge tests
# ---------------------------------------------------------------------------

class TestCompoundJudge:

    async def test_and_both_pass(self):
        """AND combiner: both judges PASS → PASS"""
        j1 = make_always_pass_judge()
        j2 = make_always_pass_judge()
        compound = CompoundJudge(judges=[j1, j2], combiner="and_")
        verdict = await compound.judge(make_ctx())
        assert verdict.passed is True

    async def test_and_first_pass_second_fail(self):
        """AND combiner: first PASS, second FAIL → FAIL (short-circuit on FAIL)"""
        j1 = make_always_pass_judge()
        j2 = make_always_fail_judge()
        compound = CompoundJudge(judges=[j1, j2], combiner="and_")
        verdict = await compound.judge(make_ctx())
        assert verdict.passed is False
        # Both judges are called because j1 PASS doesn't short-circuit AND
        j1.judge.assert_called_once()
        j2.judge.assert_called_once()

    async def test_or_first_pass_short_circuits(self):
        """OR combiner: first judge PASS → PASS immediately (second irrelevant)"""
        j1 = make_always_pass_judge()
        j2 = make_always_fail_judge()
        compound = CompoundJudge(judges=[j1, j2], combiner="or_")
        verdict = await compound.judge(make_ctx())
        assert verdict.passed is True
        # j2 should NOT be called because j1 already PASSed
        j1.judge.assert_called_once()
        j2.judge.assert_not_called()

    async def test_or_both_fail(self):
        """OR combiner: both judges FAIL → FAIL"""
        j1 = make_always_fail_judge()
        j2 = make_always_fail_judge()
        compound = CompoundJudge(judges=[j1, j2], combiner="or_")
        verdict = await compound.judge(make_ctx())
        assert verdict.passed is False


# ---------------------------------------------------------------------------
# JudgeRegistry tests
# ---------------------------------------------------------------------------

class TestJudgeRegistry:

    def test_create_llm_judge(self):
        """JudgeRegistry.create('llm', provider=...) returns LLMJudge"""
        provider = make_mock_provider("PASS")
        judge = JudgeRegistry.create("llm", provider=provider)
        assert isinstance(judge, LLMJudge)

    def test_create_regex_judge(self):
        """JudgeRegistry.create('regex', pattern='secret') returns RegexJudge"""
        judge = JudgeRegistry.create("regex", pattern="secret")
        assert isinstance(judge, RegexJudge)

    def test_create_unknown_raises_key_error(self):
        """JudgeRegistry.create('unknown') raises KeyError"""
        with pytest.raises(KeyError):
            JudgeRegistry.create("unknown")
