"""
redteam4rag/providers/base.py

LLMProvider Protocol and LLMProviderFactory.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol that all LLM provider implementations must satisfy."""

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
        timeout: float = 30.0,
    ) -> str: ...

    async def complete_json(
        self,
        prompt: str,
        schema: dict | None = None,
        temperature: float = 0.0,
        system_prompt: str | None = None,
    ) -> dict: ...

    async def batch_complete(
        self,
        prompts: list[str],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> list[str]: ...

    def get_model_name(self) -> str: ...


class LLMProviderFactory:
    """Factory that creates LLMProvider instances by name."""

    @staticmethod
    def create(
        provider_name: str,
        api_key: str,
        model: str,
        **kwargs: Any,
    ) -> LLMProvider:
        """
        Resolve provider_name to a concrete LLMProvider class and instantiate it.

        Args:
            provider_name: One of "anthropic", "openai", "ollama".
            api_key: API key (or empty string for local providers like ollama).
            model: Model identifier string.
            **kwargs: Additional keyword arguments forwarded to the provider constructor.

        Returns:
            A concrete LLMProvider instance.

        Raises:
            ValueError: If provider_name is not recognised.
        """
        name = provider_name.lower().strip()

        if name == "anthropic":
            from redteam4rag.providers.anthropic import AnthropicProvider
            return AnthropicProvider(api_key=api_key, model=model, **kwargs)

        if name == "openai":
            from redteam4rag.providers.openai import OpenAIProvider
            return OpenAIProvider(api_key=api_key, model=model, **kwargs)

        if name == "ollama":
            raise ValueError(
                "Ollama provider is not yet implemented. "
                "Supported providers: anthropic, openai."
            )

        raise ValueError(
            f"Unknown LLM provider: {provider_name!r}. "
            "Supported providers: anthropic, openai."
        )
