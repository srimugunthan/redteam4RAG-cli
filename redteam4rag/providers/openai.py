"""
redteam4rag/providers/openai.py

OpenAIProvider — wraps openai.AsyncOpenAI to implement LLMProvider.
"""

from __future__ import annotations

import asyncio
import json
import re

try:
    from openai import AsyncOpenAI
except ImportError as e:
    raise ImportError(
        "openai package is required for OpenAIProvider. "
        "Install it with: pip install 'redteam4rag[openai]'"
    ) from e


class OpenAIProvider:
    """LLM provider backed by the OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key)

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
        """Send a single chat completion request and return the response text."""
        messages: list[dict] = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
        )
        return response.choices[0].message.content

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
                f"OpenAIProvider.complete_json: could not parse response as JSON. "
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
