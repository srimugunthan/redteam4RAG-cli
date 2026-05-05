"""
redteam4rag/judges/compound.py

CompoundJudge — aggregates multiple judges with AND / OR short-circuit logic.
"""

from __future__ import annotations

from redteam4rag.judges.base import BaseJudge
from redteam4rag.models import JudgeContext, JudgeVerdict


class CompoundJudge(BaseJudge):
    """
    Runs a list of judges and combines their verdicts.

    Parameters
    ----------
    judges:
        Ordered list of ``BaseJudge`` instances to run.
    combiner:
        ``"and_"`` — all judges must PASS; short-circuits on first FAIL.
        ``"or_"``  — any judge must PASS; short-circuits on first PASS.
    judge_name:
        Label stored in the returned ``JudgeVerdict``.
    """

    def __init__(
        self,
        judges: list[BaseJudge],
        combiner: str = "and_",
        judge_name: str = "compound",
    ) -> None:
        if combiner not in ("and_", "or_"):
            raise ValueError(
                f"combiner must be 'and_' or 'or_', got {combiner!r}"
            )
        self._judges = judges
        self._combiner = combiner
        self._judge_name = judge_name

    async def judge(self, ctx: JudgeContext) -> JudgeVerdict:
        collected_reasonings: list[str] = []

        if self._combiner == "and_":
            for j in self._judges:
                verdict = await j.judge(ctx)
                collected_reasonings.append(verdict.reasoning)
                if not verdict.passed:
                    # Short-circuit on first FAIL
                    return JudgeVerdict(
                        passed=False,
                        reasoning=" | ".join(collected_reasonings),
                        judge_name=self._judge_name,
                    )
            # All judges passed
            return JudgeVerdict(
                passed=True,
                reasoning=" | ".join(collected_reasonings),
                judge_name=self._judge_name,
            )

        else:  # combiner == "or_"
            for j in self._judges:
                verdict = await j.judge(ctx)
                collected_reasonings.append(verdict.reasoning)
                if verdict.passed:
                    # Short-circuit on first PASS
                    return JudgeVerdict(
                        passed=True,
                        reasoning=" | ".join(collected_reasonings),
                        judge_name=self._judge_name,
                    )
            # All judges failed
            return JudgeVerdict(
                passed=False,
                reasoning=" | ".join(collected_reasonings),
                judge_name=self._judge_name,
            )
