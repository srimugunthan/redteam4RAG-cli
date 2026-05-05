"""
redteam4rag/judges/registry.py

JudgeRegistry — maps string names to BaseJudge subclasses and instantiates them.
"""

from __future__ import annotations

from redteam4rag.judges.base import BaseJudge
from redteam4rag.providers.base import LLMProvider


class JudgeRegistry:
    """Central registry for judge classes."""

    _registry: dict[str, type[BaseJudge]] = {}

    @classmethod
    def register(cls, name: str, judge_cls: type[BaseJudge]) -> None:
        """Register a judge class under the given name."""
        cls._registry[name] = judge_cls

    @classmethod
    def create(
        cls,
        spec: str,
        provider: LLMProvider | None = None,
        **kwargs,
    ) -> BaseJudge:
        """
        Instantiate a judge from a spec string.

        Spec forms
        ----------
        ``"llm"``              → LLMJudge(provider=provider)
        ``"llm:model-name"``   → LLMJudge(provider=provider)  (model hint ignored here)
        ``"regex"``            → RegexJudge(pattern=kwargs.get("pattern", ""))
        ``"regex:pattern"``    → RegexJudge(pattern="pattern")
        ``"compound"``         → CompoundJudge(judges=kwargs.get("judges", []))

        Raises
        ------
        KeyError
            If the base name (before the first ``:``) is not registered.
        """
        # Split on the first colon to separate kind from optional extra
        parts = spec.split(":", 1)
        kind = parts[0].strip()
        extra = parts[1] if len(parts) > 1 else None

        if kind not in cls._registry:
            raise KeyError(f"No judge registered under {kind!r}. Available: {list(cls._registry)}")

        judge_cls = cls._registry[kind]

        # Lazy imports to avoid circular import at module level
        from redteam4rag.judges.llm import LLMJudge
        from redteam4rag.judges.regex import RegexJudge
        from redteam4rag.judges.compound import CompoundJudge

        if issubclass(judge_cls, LLMJudge):
            if provider is None:
                raise ValueError("An LLMProvider instance is required to create an LLMJudge.")
            return LLMJudge(provider=provider, **kwargs)

        if issubclass(judge_cls, RegexJudge):
            pattern = extra if extra is not None else kwargs.get("pattern", "")
            kw = {k: v for k, v in kwargs.items() if k != "pattern"}
            return RegexJudge(pattern=pattern, **kw)

        if issubclass(judge_cls, CompoundJudge):
            return CompoundJudge(**kwargs)

        # Generic fallback — attempt to instantiate with remaining kwargs
        return judge_cls(**kwargs)


# ---------------------------------------------------------------------------
# Register built-in judges
# ---------------------------------------------------------------------------
from redteam4rag.judges.llm import LLMJudge          # noqa: E402
from redteam4rag.judges.regex import RegexJudge       # noqa: E402
from redteam4rag.judges.compound import CompoundJudge  # noqa: E402

JudgeRegistry.register("llm", LLMJudge)
JudgeRegistry.register("regex", RegexJudge)
JudgeRegistry.register("compound", CompoundJudge)
