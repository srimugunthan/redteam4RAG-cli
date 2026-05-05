"""
redteam4rag/providers/anthropic.py

AnthropicProvider — wraps anthropic.AsyncAnthropic to implement LLMProvider.
"""

from __future__ import annotations

import asyncio
import json
import re

import anthropic


class AnthropicProvider:
    """LLM provider backed by the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
        timeout: float = 30.0,
    ) -> str:
        """Send a single completion request and return the response text."""
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt is not None:
            kwargs["system"] = system_prompt

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text

    async def complete_json(
        self,
        prompt: str,
        schema: dict | None = None,
        temperature: float = 0.0,
        system_prompt: str | None = None,
    ) -> dict:
        """
        Request a JSON completion and return a parsed dict.

        Strips markdown code fences (```json … ``` or ``` … ```) if present.
        Raises ValueError if the response cannot be parsed as JSON.
        """
        raw = await self.complete(
            prompt=prompt,
            temperature=temperature,
            system_prompt=system_prompt,
        )
        text = _strip_markdown_fences(raw)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"AnthropicProvider.complete_json: could not parse response as JSON. "
                f"Raw text: {raw!r}"
            ) from exc

    async def batch_complete(
        self,
        prompts: list[str],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> list[str]:
        """Run N complete() calls concurrently and return results in order."""
        tasks = [
            self.complete(prompt=p, temperature=temperature, max_tokens=max_tokens)
            for p in prompts
        ]
        return list(await asyncio.gather(*tasks))

    def get_model_name(self) -> str:
        """Return the model identifier this provider was initialised with."""
        return self._model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences from *text* if present."""
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped
