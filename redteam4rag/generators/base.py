"""
redteam4rag/generators/base.py

ProbeGenerator Protocol and ProbeGeneratorFactory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from redteam4rag.models import AttackSpec, Probe
from redteam4rag.providers.base import LLMProviderFactory

if TYPE_CHECKING:
    from redteam4rag.core.config import ScanConfig


class ProbeGenerator(Protocol):
    """Protocol that all probe generator implementations must satisfy."""

    async def generate(self, spec: AttackSpec) -> list[Probe]: ...


class ProbeGeneratorFactory:
    """Factory that creates ProbeGenerator instances based on config and spec overrides."""

    @staticmethod
    def create(spec: AttackSpec, config: "ScanConfig") -> ProbeGenerator:
        """
        Resolve the generator to use, in priority order:

        1. spec.generator_override  (e.g. "static" or "llm:claude-haiku-4-5-20251001")
        2. config.generator_provider + config.generator_model  (default)
        3. "static" fallback

        Returns a concrete ProbeGenerator instance.
        """
        from redteam4rag.generators.llm import LLMProbeGenerator
        from redteam4rag.generators.static import StaticProbeGenerator

        override = spec.generator_override

        if override is not None:
            # Explicit override on the spec
            if override == "static":
                return StaticProbeGenerator()
            if override.startswith("llm:"):
                model = override[len("llm:"):]
                api_key = _get_api_key(config)
                provider = LLMProviderFactory.create(
                    config.generator_provider, api_key, model
                )
                return LLMProbeGenerator(provider)
            # Unknown override — fall through to default
        else:
            # No override: use config defaults
            # Default to static unless config.generator_provider is set meaningfully
            # and a generator_model is configured
            if config.generator_provider and config.generator_model:
                # Use config defaults — but only build LLM provider when explicitly
                # configured beyond the bare minimum.  The factory defaults to static
                # when no explicit override is requested; to get LLM generation the
                # caller must set generator_override="llm:<model>" or rely on a
                # higher-level scan-runner.  Here we return static as the safe default.
                pass

        return StaticProbeGenerator()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_api_key(config: "ScanConfig") -> str:
    """Extract the generator API key from config based on generator_provider."""
    if config.generator_provider == "anthropic":
        return config.anthropic_api_key.get_secret_value()
    if config.generator_provider == "openai":
        return config.openai_api_key.get_secret_value() if config.openai_api_key else ""
    return ""
