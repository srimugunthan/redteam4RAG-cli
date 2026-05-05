"""
redteam4rag/conversation/base.py

ConversationStrategy Protocol and ConversationStrategyFactory.
"""

from __future__ import annotations

from typing import Protocol

from redteam4rag.models import RawResponse, JudgeVerdict
from redteam4rag.conversation.static import StaticConversation


class ConversationStrategy(Protocol):
    async def initialize(self, seed_query: str) -> None: ...

    async def next_turn(
        self,
        history: list[tuple[str, RawResponse]],
        current_verdict: JudgeVerdict | None = None,
    ) -> str | None:
        """Return the next query string, or None when conversation is exhausted."""
        ...

    async def should_continue(
        self,
        history: list[tuple[str, RawResponse]],
        verdict: JudgeVerdict,
    ) -> bool:
        """Return True if the conversation should continue after this verdict."""
        ...

    def get_metadata(self) -> dict: ...


class ConversationStrategyFactory:
    @staticmethod
    def create(seed_query: str, strategy_name: str = "static") -> ConversationStrategy:
        if strategy_name == "static":
            return StaticConversation(turns=[seed_query])
        raise ValueError(f"Unknown conversation strategy: {strategy_name!r}")
