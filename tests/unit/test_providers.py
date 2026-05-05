"""
tests/unit/test_providers.py

Unit tests for the LLM provider layer (Phase 2B).
All external SDK calls are mocked — no real API calls are made.
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anthropic_response(text: str) -> MagicMock:
    """Build a mock object that looks like anthropic.types.Message."""
    content_item = MagicMock()
    content_item.text = text
    response = MagicMock()
    response.content = [content_item]
    return response


def _make_openai_response(text: str) -> MagicMock:
    """Build a mock object that looks like openai.types.chat.ChatCompletion."""
    message = MagicMock()
    message.content = text
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# AnthropicProvider tests
# ---------------------------------------------------------------------------

class TestAnthropicProviderComplete:
    async def test_returns_text(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        mock_create = AsyncMock(return_value=_make_anthropic_response("hello world"))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test", model="claude-sonnet-4-6")
            result = await provider.complete("Say hello")

        assert result == "hello world"

    async def test_passes_correct_model_and_max_tokens(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        mock_create = AsyncMock(return_value=_make_anthropic_response("ok"))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test", model="claude-opus-4-5")
            await provider.complete("ping", max_tokens=512, temperature=0.5)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "claude-opus-4-5"
        assert call_kwargs["max_tokens"] == 512
        assert call_kwargs["temperature"] == 0.5

    async def test_passes_system_prompt_when_provided(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        mock_create = AsyncMock(return_value=_make_anthropic_response("ok"))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test")
            await provider.complete("Hello", system_prompt="You are a helpful assistant.")

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["system"] == "You are a helpful assistant."

    async def test_no_system_key_when_system_prompt_is_none(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        mock_create = AsyncMock(return_value=_make_anthropic_response("ok"))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test")
            await provider.complete("Hello")

        call_kwargs = mock_create.call_args.kwargs
        assert "system" not in call_kwargs


class TestAnthropicProviderCompleteJson:
    async def test_valid_json_string_returns_dict(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        json_str = '{"verdict": true, "score": 0.9}'
        mock_create = AsyncMock(return_value=_make_anthropic_response(json_str))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test")
            result = await provider.complete_json("Rate this")

        assert result == {"verdict": True, "score": 0.9}

    async def test_markdown_fenced_json_is_parsed(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        fenced = '```json\n{"key": "val"}\n```'
        mock_create = AsyncMock(return_value=_make_anthropic_response(fenced))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test")
            result = await provider.complete_json("Give JSON")

        assert result == {"key": "val"}

    async def test_plain_fenced_json_is_parsed(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        fenced = '```\n{"key": "val"}\n```'
        mock_create = AsyncMock(return_value=_make_anthropic_response(fenced))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test")
            result = await provider.complete_json("Give JSON")

        assert result == {"key": "val"}

    async def test_invalid_json_raises_value_error(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        mock_create = AsyncMock(return_value=_make_anthropic_response("not json at all"))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test")
            with pytest.raises(ValueError, match="could not parse response as JSON"):
                await provider.complete_json("Give JSON")


class TestAnthropicProviderBatchComplete:
    async def test_batch_complete_calls_complete_n_times(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        responses = ["resp1", "resp2", "resp3"]
        side_effects = [
            _make_anthropic_response(t) for t in responses
        ]
        mock_create = AsyncMock(side_effect=side_effects)
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test")
            results = await provider.batch_complete(["p1", "p2", "p3"])

        assert mock_create.call_count == 3
        assert results == ["resp1", "resp2", "resp3"]

    async def test_batch_complete_returns_list(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        mock_create = AsyncMock(return_value=_make_anthropic_response("x"))
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value.messages.create = mock_create
            provider = AnthropicProvider(api_key="sk-ant-test")
            results = await provider.batch_complete(["a", "b"])

        assert isinstance(results, list)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# get_model_name tests
# ---------------------------------------------------------------------------

class TestGetModelName:
    def test_anthropic_returns_model_string(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        with patch("anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="sk-ant-test", model="claude-haiku-3-5")

        assert provider.get_model_name() == "claude-haiku-3-5"

    def test_anthropic_default_model(self):
        from redteam4rag.providers.anthropic import AnthropicProvider

        with patch("anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(api_key="sk-ant-test")

        assert provider.get_model_name() == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# LLMProviderFactory tests
# ---------------------------------------------------------------------------

class TestLLMProviderFactory:
    def test_create_anthropic_returns_anthropic_provider(self):
        from redteam4rag.providers.anthropic import AnthropicProvider
        from redteam4rag.providers.base import LLMProviderFactory

        with patch("anthropic.AsyncAnthropic"):
            provider = LLMProviderFactory.create(
                "anthropic", api_key="sk-ant-test", model="claude-sonnet-4-6"
            )

        assert isinstance(provider, AnthropicProvider)

    def test_create_openai_returns_openai_provider(self):
        """
        OpenAI may or may not be installed in the test environment.
        We mock the openai module at the sys.modules level to avoid
        an ImportError regardless of whether the package is installed.
        """
        # Build a minimal fake openai module
        fake_openai = types.ModuleType("openai")
        fake_async_openai = MagicMock()
        fake_openai.AsyncOpenAI = fake_async_openai

        # Patch sys.modules so that "from openai import AsyncOpenAI" resolves our fake
        openai_mod_name = "openai"
        provider_mod_name = "redteam4rag.providers.openai"

        # Remove the cached provider module so it re-imports with the fake openai
        sys.modules.pop(provider_mod_name, None)

        with patch.dict(sys.modules, {openai_mod_name: fake_openai}):
            # Re-import the provider module under the fake openai
            openai_provider_mod = importlib.import_module(provider_mod_name)
            OpenAIProvider = openai_provider_mod.OpenAIProvider

            provider = LLMProviderFactory_create_openai(OpenAIProvider, fake_async_openai)

        assert isinstance(provider, OpenAIProvider)

    def test_create_unknown_raises_value_error(self):
        from redteam4rag.providers.base import LLMProviderFactory

        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMProviderFactory.create(
                "unknown_provider", api_key="x", model="y"
            )

    def test_create_ollama_raises_value_error(self):
        from redteam4rag.providers.base import LLMProviderFactory

        with pytest.raises(ValueError, match="not yet implemented"):
            LLMProviderFactory.create("ollama", api_key="", model="llama3")


# ---------------------------------------------------------------------------
# OpenAIProvider tests  (mocked openai module)
# ---------------------------------------------------------------------------

class TestOpenAIProvider:
    """
    All tests in this class patch sys.modules["openai"] before importing
    OpenAIProvider so that the real openai package is never required.
    """

    def _get_provider_class(self, fake_async_openai_cls):
        """Re-import OpenAIProvider under a fake openai module."""
        fake_openai = types.ModuleType("openai")
        fake_openai.AsyncOpenAI = fake_async_openai_cls

        sys.modules.pop("redteam4rag.providers.openai", None)
        with patch.dict(sys.modules, {"openai": fake_openai}):
            mod = importlib.import_module("redteam4rag.providers.openai")
            return mod.OpenAIProvider

    async def test_complete_returns_text(self):
        fake_instance = MagicMock()
        fake_instance.chat.completions.create = AsyncMock(
            return_value=_make_openai_response("openai reply")
        )
        fake_cls = MagicMock(return_value=fake_instance)

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")
        result = await provider.complete("Hello")

        assert result == "openai reply"

    async def test_complete_passes_system_prompt(self):
        fake_instance = MagicMock()
        mock_create = AsyncMock(return_value=_make_openai_response("ok"))
        fake_instance.chat.completions.create = mock_create
        fake_cls = MagicMock(return_value=fake_instance)

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4o")
        await provider.complete("Hello", system_prompt="Be concise.")

        messages = mock_create.call_args.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "Be concise."}
        assert messages[1] == {"role": "user", "content": "Hello"}

    async def test_complete_no_system_prompt_by_default(self):
        fake_instance = MagicMock()
        mock_create = AsyncMock(return_value=_make_openai_response("ok"))
        fake_instance.chat.completions.create = mock_create
        fake_cls = MagicMock(return_value=fake_instance)

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test")
        await provider.complete("Hello")

        messages = mock_create.call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    async def test_complete_json_parses_valid_json(self):
        fake_instance = MagicMock()
        fake_instance.chat.completions.create = AsyncMock(
            return_value=_make_openai_response('{"score": 1}')
        )
        fake_cls = MagicMock(return_value=fake_instance)

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test")
        result = await provider.complete_json("Give JSON")

        assert result == {"score": 1}

    async def test_complete_json_strips_markdown_fences(self):
        fake_instance = MagicMock()
        fake_instance.chat.completions.create = AsyncMock(
            return_value=_make_openai_response('```json\n{"k": "v"}\n```')
        )
        fake_cls = MagicMock(return_value=fake_instance)

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test")
        result = await provider.complete_json("Give JSON")

        assert result == {"k": "v"}

    async def test_complete_json_raises_on_invalid_json(self):
        fake_instance = MagicMock()
        fake_instance.chat.completions.create = AsyncMock(
            return_value=_make_openai_response("not valid json")
        )
        fake_cls = MagicMock(return_value=fake_instance)

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test")
        with pytest.raises(ValueError, match="could not parse response as JSON"):
            await provider.complete_json("Give JSON")

    async def test_batch_complete_calls_n_times(self):
        fake_instance = MagicMock()
        mock_create = AsyncMock(return_value=_make_openai_response("reply"))
        fake_instance.chat.completions.create = mock_create
        fake_cls = MagicMock(return_value=fake_instance)

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test")
        results = await provider.batch_complete(["a", "b", "c"])

        assert mock_create.call_count == 3
        assert results == ["reply", "reply", "reply"]

    def test_get_model_name(self):
        fake_cls = MagicMock()

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test", model="gpt-4-turbo")

        assert provider.get_model_name() == "gpt-4-turbo"

    def test_get_model_name_default(self):
        fake_cls = MagicMock()

        OpenAIProvider = self._get_provider_class(fake_cls)
        provider = OpenAIProvider(api_key="sk-test")

        assert provider.get_model_name() == "gpt-4o"


# ---------------------------------------------------------------------------
# Helper used by TestLLMProviderFactory.test_create_openai_returns_openai_provider
# ---------------------------------------------------------------------------

def LLMProviderFactory_create_openai(OpenAIProvider, fake_async_openai_cls):  # noqa: N802
    """
    Create an OpenAIProvider through the factory without importing the real
    openai package.  We call the constructor directly since the factory itself
    would also need the patched sys.modules.
    """
    instance = OpenAIProvider(api_key="sk-test", model="gpt-4o")
    return instance
