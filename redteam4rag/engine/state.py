"""
redteam4rag/engine/state.py

AttackPayload dataclass and AttackState TypedDict for the LangGraph orchestrator.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TypedDict

from redteam4rag.models import AttackSpec, RawResponse, JudgeVerdict


@dataclass
class AttackPayload:
    """A single unit of work: one query for one AttackSpec."""

    spec: AttackSpec
    query: str
    mutation_round: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class AttackState(TypedDict):
    """LangGraph state for a single attack invocation."""

    run_id: str
    attack_queue: list[AttackPayload]
    current_attack: AttackPayload | None
    responses: list[RawResponse]
    verdict: JudgeVerdict | None
    mutation_count: int
    mutation_history: list[AttackPayload]
    mutation_exhausted: bool
    conversation_history: list[tuple[str, RawResponse]]
    conversation_metadata: dict
    strategy_metadata: dict
    results: list  # list[AttackResult] accumulated across the run
    dry_run: bool
