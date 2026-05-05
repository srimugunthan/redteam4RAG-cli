"""
redteam4rag/adapters/base.py

TargetAdapter Protocol — the interface all adapters must satisfy.
"""

from __future__ import annotations

from typing import Protocol

from redteam4rag.models import Probe, RawResponse


class TargetAdapter(Protocol):
    async def query(self, probe: Probe) -> RawResponse: ...
    async def health_check(self) -> bool: ...
