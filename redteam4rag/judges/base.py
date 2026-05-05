"""
redteam4rag/judges/base.py

Abstract base class for all judges.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from redteam4rag.models import JudgeContext, JudgeVerdict


class BaseJudge(ABC):
    """Abstract base class that every judge must implement."""

    @abstractmethod
    async def judge(self, ctx: JudgeContext) -> JudgeVerdict: ...
