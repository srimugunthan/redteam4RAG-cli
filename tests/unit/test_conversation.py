"""
tests/unit/test_conversation.py

Unit tests for Phase 3C — Conversation Strategy Layer.
asyncio_mode = "auto" is set in pyproject.toml; no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import pytest

from redteam4rag.models import RawResponse, JudgeVerdict
from redteam4rag.conversation.static import (
    StaticConversation,
    HeuristicConversation,
    LLMAdaptiveConversation,
)
from redteam4rag.conversation.base import ConversationStrategyFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_response(text: str) -> RawResponse:
    return RawResponse(status_code=200, body={}, response_text=text)


passing_verdict = JudgeVerdict(passed=True, reasoning="ok", judge_name="test")
failing_verdict = JudgeVerdict(passed=False, reasoning="vuln", judge_name="test")


# ---------------------------------------------------------------------------
# StaticConversation — basic turn sequencing
# ---------------------------------------------------------------------------

async def test_static_single_turn_first_call_returns_query():
    """First next_turn() on a single-turn conversation returns the query string."""
    conv = StaticConversation(turns=["hello world"])
    result = await conv.next_turn(history=[], current_verdict=None)
    assert result == "hello world"


async def test_static_single_turn_second_call_returns_none():
    """Second next_turn() on a single-turn conversation returns None (exhausted)."""
    conv = StaticConversation(turns=["hello world"])
    await conv.next_turn(history=[], current_verdict=None)
    result = await conv.next_turn(history=[], current_verdict=None)
    assert result is None


async def test_static_three_turns_returns_each_in_order_then_none():
    """Three-turn conversation returns each query in order, then None on the 4th call."""
    turns = ["turn-1", "turn-2", "turn-3"]
    conv = StaticConversation(turns=turns)
    history: list[tuple[str, RawResponse]] = []

    assert await conv.next_turn(history) == "turn-1"
    assert await conv.next_turn(history) == "turn-2"
    assert await conv.next_turn(history) == "turn-3"
    assert await conv.next_turn(history) is None


# ---------------------------------------------------------------------------
# StaticConversation — should_continue
# ---------------------------------------------------------------------------

async def test_static_should_continue_true_when_turns_remain():
    """should_continue() returns True when there are unconsumed turns."""
    conv = StaticConversation(turns=["q1", "q2"])
    await conv.next_turn(history=[])          # consume first turn; index → 1
    result = await conv.should_continue(history=[], verdict=passing_verdict)
    assert result is True


async def test_static_should_continue_false_when_exhausted():
    """should_continue() returns False after all turns have been consumed."""
    conv = StaticConversation(turns=["q1"])
    await conv.next_turn(history=[])          # consume the only turn; index → 1
    result = await conv.should_continue(history=[], verdict=passing_verdict)
    assert result is False


# ---------------------------------------------------------------------------
# StaticConversation — get_metadata
# ---------------------------------------------------------------------------

def test_static_metadata_before_any_turns():
    """get_metadata() before any turns: turn_index=0, total_turns=1."""
    conv = StaticConversation(turns=["q"])
    meta = conv.get_metadata()
    assert meta == {"turn_index": 0, "total_turns": 1}


async def test_static_metadata_after_one_turn_consumed():
    """get_metadata() after one turn consumed: turn_index=1, total_turns=1."""
    conv = StaticConversation(turns=["q"])
    await conv.next_turn(history=[])
    meta = conv.get_metadata()
    assert meta == {"turn_index": 1, "total_turns": 1}


# ---------------------------------------------------------------------------
# StaticConversation — initialize (reset)
# ---------------------------------------------------------------------------

async def test_static_initialize_resets_index():
    """After exhausting turns, initialize() resets so next_turn() returns first turn again."""
    conv = StaticConversation(turns=["first"])
    await conv.next_turn(history=[])          # exhaust
    assert await conv.next_turn(history=[]) is None

    await conv.initialize(seed_query="first")  # reset
    result = await conv.next_turn(history=[])
    assert result == "first"


# ---------------------------------------------------------------------------
# ConversationStrategyFactory
# ---------------------------------------------------------------------------

def test_factory_create_static_explicit():
    """ConversationStrategyFactory.create with strategy_name='static' returns StaticConversation."""
    strategy = ConversationStrategyFactory.create("my query", "static")
    assert isinstance(strategy, StaticConversation)


def test_factory_create_default_is_static():
    """ConversationStrategyFactory.create with no strategy_name defaults to StaticConversation."""
    strategy = ConversationStrategyFactory.create("my query")
    assert isinstance(strategy, StaticConversation)


def test_factory_create_unknown_raises_value_error():
    """ConversationStrategyFactory.create with unknown strategy raises ValueError containing the name."""
    with pytest.raises(ValueError, match="unknown"):
        ConversationStrategyFactory.create("q", "unknown")


# ---------------------------------------------------------------------------
# Stub strategies — NotImplementedError
# ---------------------------------------------------------------------------

async def test_heuristic_conversation_initialize_raises():
    """HeuristicConversation.initialize() raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        await HeuristicConversation().initialize("q")


async def test_llm_adaptive_conversation_initialize_raises():
    """LLMAdaptiveConversation.initialize() raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        await LLMAdaptiveConversation().initialize("q")
