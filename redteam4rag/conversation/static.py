"""
redteam4rag/conversation/static.py

Concrete ConversationStrategy implementations.
StaticConversation is the only production-ready strategy in v1.0.
HeuristicConversation and LLMAdaptiveConversation are stubs planned for v1.1.
"""

from __future__ import annotations

from redteam4rag.models import RawResponse, JudgeVerdict


class StaticConversation:
    """Single-pass static conversation strategy — plays a fixed list of turns in order."""

    def __init__(self, turns: list[str]) -> None:
        self._turns = turns
        self._index = 0

    async def initialize(self, seed_query: str) -> None:
        self._index = 0  # reset on each new attack

    async def next_turn(
        self,
        history: list[tuple[str, RawResponse]],
        current_verdict: JudgeVerdict | None = None,
    ) -> str | None:
        if self._index >= len(self._turns):
            return None
        query = self._turns[self._index]
        self._index += 1
        return query

    async def should_continue(
        self,
        history: list[tuple[str, RawResponse]],
        verdict: JudgeVerdict,
    ) -> bool:
        return self._index < len(self._turns)

    def get_metadata(self) -> dict:
        return {"turn_index": self._index, "total_turns": len(self._turns)}


class HeuristicConversation:
    """v1.1 — heuristic multi-turn follow-up strategy."""

    async def initialize(self, seed_query: str) -> None:
        raise NotImplementedError("HeuristicConversation is planned for v1.1")

    async def next_turn(
        self,
        history: list[tuple[str, RawResponse]],
        current_verdict: JudgeVerdict | None = None,
    ) -> str | None:
        raise NotImplementedError("HeuristicConversation is planned for v1.1")

    async def should_continue(
        self,
        history: list[tuple[str, RawResponse]],
        verdict: JudgeVerdict,
    ) -> bool:
        raise NotImplementedError("HeuristicConversation is planned for v1.1")

    def get_metadata(self) -> dict:
        raise NotImplementedError("HeuristicConversation is planned for v1.1")


class LLMAdaptiveConversation:
    """v1.1 — LLM-driven adaptive conversation strategy."""

    async def initialize(self, seed_query: str) -> None:
        raise NotImplementedError("LLMAdaptiveConversation is planned for v1.1")

    async def next_turn(
        self,
        history: list[tuple[str, RawResponse]],
        current_verdict: JudgeVerdict | None = None,
    ) -> str | None:
        raise NotImplementedError("LLMAdaptiveConversation is planned for v1.1")

    async def should_continue(
        self,
        history: list[tuple[str, RawResponse]],
        verdict: JudgeVerdict,
    ) -> bool:
        raise NotImplementedError("LLMAdaptiveConversation is planned for v1.1")

    def get_metadata(self) -> dict:
        raise NotImplementedError("LLMAdaptiveConversation is planned for v1.1")
