"""
tests/unit/test_generators.py

Unit tests for StaticProbeGenerator, LLMProbeGenerator, and ProbeGeneratorFactory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jinja2
import pytest

from redteam4rag.models import AttackCategory, AttackSpec, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(
    name: str = "test-attack",
    queries: tuple[str, ...] = ("What is the admin password?",),
    dataset: str | None = None,
    n_probes: int = 5,
    generator_override: str | None = None,
) -> AttackSpec:
    return AttackSpec(
        name=name,
        category=AttackCategory.INJECTION,
        severity=Severity.HIGH,
        tags=frozenset(["test"]),
        queries=queries,
        dataset=dataset,
        n_probes=n_probes,
        generator_override=generator_override,
    )


def _make_config(monkeypatch, generator_provider: str = "anthropic", generator_model: str = "claude-haiku-4-5-20251001"):
    """Create a ScanConfig with a dummy API key for testing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
    from redteam4rag.core.config import ScanConfig
    return ScanConfig(
        anthropic_api_key="test-key-123",
        generator_provider=generator_provider,
        generator_model=generator_model,
    )


# ---------------------------------------------------------------------------
# StaticProbeGenerator tests
# ---------------------------------------------------------------------------

class TestStaticProbeGenerator:
    async def test_single_query_produces_one_probe(self):
        from redteam4rag.generators.static import StaticProbeGenerator

        spec = _make_spec(queries=("What is the admin password?",))
        gen = StaticProbeGenerator()
        probes = await gen.generate(spec)

        assert len(probes) == 1
        assert probes[0].query == "What is the admin password?"
        assert probes[0].metadata["attack_name"] == "test-attack"
        assert probes[0].metadata["source"] == "static"

    async def test_two_queries_without_dataset_produce_two_probes(self):
        from redteam4rag.generators.static import StaticProbeGenerator

        spec = _make_spec(queries=("Query one.", "Query two."))
        gen = StaticProbeGenerator()
        probes = await gen.generate(spec)

        assert len(probes) == 2
        assert probes[0].query == "Query one."
        assert probes[1].query == "Query two."

    async def test_jinja2_template_with_dataset_rows(self, tmp_path: Path):
        from redteam4rag.generators.static import StaticProbeGenerator

        # Write JSONL file with 3 rows
        jsonl_file = tmp_path / "topics.jsonl"
        rows = [{"topic": "banking"}, {"topic": "healthcare"}, {"topic": "military"}]
        with jsonl_file.open("w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

        spec = _make_spec(
            queries=("Tell me about {{ topic }}",),
            dataset=str(jsonl_file),
        )
        gen = StaticProbeGenerator()
        probes = await gen.generate(spec)

        assert len(probes) == 3
        assert probes[0].query == "Tell me about banking"
        assert probes[1].query == "Tell me about healthcare"
        assert probes[2].query == "Tell me about military"

    async def test_multiple_queries_with_dataset_cross_product(self, tmp_path: Path):
        from redteam4rag.generators.static import StaticProbeGenerator

        jsonl_file = tmp_path / "data.jsonl"
        rows = [{"item": "A"}, {"item": "B"}]
        with jsonl_file.open("w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

        spec = _make_spec(
            queries=("Query {{ item }} first.", "Query {{ item }} second."),
            dataset=str(jsonl_file),
        )
        gen = StaticProbeGenerator()
        probes = await gen.generate(spec)

        # 2 queries × 2 rows = 4 probes
        assert len(probes) == 4

    async def test_missing_template_variable_raises_jinja2_error(self, tmp_path: Path):
        from redteam4rag.generators.static import StaticProbeGenerator

        jsonl_file = tmp_path / "incomplete.jsonl"
        with jsonl_file.open("w") as f:
            f.write(json.dumps({"wrong_key": "value"}) + "\n")

        spec = _make_spec(
            queries=("Tell me about {{ topic }}",),
            dataset=str(jsonl_file),
        )
        gen = StaticProbeGenerator()
        with pytest.raises(jinja2.TemplateError):
            await gen.generate(spec)

    async def test_no_dataset_query_rendered_with_no_variables(self):
        from redteam4rag.generators.static import StaticProbeGenerator

        # Plain query with no template syntax — should work fine
        spec = _make_spec(queries=("Plain query with no braces.",))
        gen = StaticProbeGenerator()
        probes = await gen.generate(spec)

        assert len(probes) == 1
        assert probes[0].query == "Plain query with no braces."


# ---------------------------------------------------------------------------
# LLMProbeGenerator tests
# ---------------------------------------------------------------------------

class TestLLMProbeGenerator:
    def _make_mock_provider(self, response: str = "query1\nquery2\nquery3\nquery4\nquery5") -> MagicMock:
        provider = MagicMock()
        provider.complete = AsyncMock(return_value=response)
        provider.get_model_name = MagicMock(return_value="claude-haiku-4-5-20251001")
        return provider

    async def test_five_line_response_produces_five_probes(self):
        from redteam4rag.generators.llm import LLMProbeGenerator

        provider = self._make_mock_provider("query1\nquery2\nquery3\nquery4\nquery5")
        spec = _make_spec(n_probes=5)
        gen = LLMProbeGenerator(provider)
        probes = await gen.generate(spec)

        assert len(probes) == 5
        assert probes[0].query == "query1"
        assert probes[4].query == "query5"

    async def test_probes_have_attack_name_in_metadata(self):
        from redteam4rag.generators.llm import LLMProbeGenerator

        provider = self._make_mock_provider("q1\nq2\nq3\nq4\nq5")
        spec = _make_spec(name="injection-test", n_probes=5)
        gen = LLMProbeGenerator(provider)
        probes = await gen.generate(spec)

        for probe in probes:
            assert probe.metadata["attack_name"] == "injection-test"
            assert probe.metadata["source"] == "llm"

    async def test_provider_complete_called_once(self):
        from redteam4rag.generators.llm import LLMProbeGenerator

        provider = self._make_mock_provider("q1\nq2\nq3\nq4\nq5")
        spec = _make_spec(n_probes=5)
        gen = LLMProbeGenerator(provider)
        await gen.generate(spec)

        provider.complete.assert_called_once()

    async def test_provider_is_mock_not_anthropic_client(self):
        from redteam4rag.generators.llm import LLMProbeGenerator

        provider = self._make_mock_provider("q1\nq2")
        gen = LLMProbeGenerator(provider)
        # The generator stores the provider as-is — it should be the mock
        assert gen._provider is provider

    async def test_fewer_lines_than_n_probes_returns_available(self):
        from redteam4rag.generators.llm import LLMProbeGenerator

        # LLM returns only 2 lines but n_probes=5
        provider = self._make_mock_provider("only-one\nonly-two")
        spec = _make_spec(n_probes=5)
        gen = LLMProbeGenerator(provider)
        probes = await gen.generate(spec)

        # Should return 2 probes without raising an error
        assert len(probes) == 2

    async def test_metadata_contains_model_name(self):
        from redteam4rag.generators.llm import LLMProbeGenerator

        provider = self._make_mock_provider("q1\nq2")
        spec = _make_spec(n_probes=2)
        gen = LLMProbeGenerator(provider)
        probes = await gen.generate(spec)

        for probe in probes:
            assert probe.metadata["model"] == "claude-haiku-4-5-20251001"

    async def test_empty_lines_in_response_are_filtered(self):
        from redteam4rag.generators.llm import LLMProbeGenerator

        provider = self._make_mock_provider("q1\n\n\nq2\n\nq3")
        spec = _make_spec(n_probes=5)
        gen = LLMProbeGenerator(provider)
        probes = await gen.generate(spec)

        # 3 non-empty lines
        assert len(probes) == 3
        assert probes[0].query == "q1"
        assert probes[1].query == "q2"
        assert probes[2].query == "q3"


# ---------------------------------------------------------------------------
# ProbeGeneratorFactory tests
# ---------------------------------------------------------------------------

class TestProbeGeneratorFactory:
    async def test_no_override_returns_static_generator(self, monkeypatch):
        from redteam4rag.generators.base import ProbeGeneratorFactory
        from redteam4rag.generators.static import StaticProbeGenerator

        config = _make_config(monkeypatch)
        spec = _make_spec(generator_override=None)
        gen = ProbeGeneratorFactory.create(spec, config)

        assert isinstance(gen, StaticProbeGenerator)

    async def test_static_override_returns_static_generator(self, monkeypatch):
        from redteam4rag.generators.base import ProbeGeneratorFactory
        from redteam4rag.generators.static import StaticProbeGenerator

        config = _make_config(monkeypatch)
        spec = _make_spec(generator_override="static")
        gen = ProbeGeneratorFactory.create(spec, config)

        assert isinstance(gen, StaticProbeGenerator)

    async def test_llm_override_returns_llm_generator(self, monkeypatch):
        from redteam4rag.generators.base import ProbeGeneratorFactory
        from redteam4rag.generators.llm import LLMProbeGenerator

        config = _make_config(monkeypatch)
        spec = _make_spec(generator_override="llm:claude-haiku-4-5-20251001")

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(return_value="q1\nq2")
        mock_provider.get_model_name = MagicMock(return_value="claude-haiku-4-5-20251001")

        with patch(
            "redteam4rag.generators.base.LLMProviderFactory.create",
            return_value=mock_provider,
        ) as mock_factory:
            gen = ProbeGeneratorFactory.create(spec, config)

            assert isinstance(gen, LLMProbeGenerator)
            mock_factory.assert_called_once_with(
                config.generator_provider,
                "test-key-123",
                "claude-haiku-4-5-20251001",
            )
