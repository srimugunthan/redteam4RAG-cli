"""
redteam4rag/judges/regex.py

RegexJudge — evaluates RAG responses using a regular expression.
"""

from __future__ import annotations

import re

from redteam4rag.judges.base import BaseJudge
from redteam4rag.models import JudgeContext, JudgeVerdict


class RegexJudge(BaseJudge):
    """
    Judge that applies a regex pattern to the system response.

    Parameters
    ----------
    pattern:
        Regular-expression string to compile and test against the response.
    match_means:
        ``"fail"`` (default) — a pattern match indicates a FAIL verdict.
        ``"pass"`` — a pattern match indicates a PASS verdict.
    judge_name:
        Label stored in the returned ``JudgeVerdict``.
    """

    def __init__(
        self,
        pattern: str,
        match_means: str = "fail",
        judge_name: str = "regex",
    ) -> None:
        if match_means not in ("fail", "pass"):
            raise ValueError(
                f"match_means must be 'fail' or 'pass', got {match_means!r}"
            )
        self._pattern: re.Pattern[str] = re.compile(pattern)  # raises re.error on bad pattern
        self._match_means = match_means
        self._judge_name = judge_name

    async def judge(self, ctx: JudgeContext) -> JudgeVerdict:
        matched = bool(self._pattern.search(ctx.response))

        if self._match_means == "fail":
            passed = not matched
            reasoning = "Pattern matched" if matched else "No pattern match"
        else:  # match_means == "pass"
            passed = matched
            reasoning = "Pattern matched" if matched else "No pattern match"

        return JudgeVerdict(
            passed=passed,
            reasoning=reasoning,
            judge_name=self._judge_name,
        )
