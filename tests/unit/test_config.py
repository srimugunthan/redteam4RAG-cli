"""
tests/unit/test_config.py — Phase 1 ScanConfig tests.
Zero network calls. Uses monkeypatch for env vars and tmp_path for .env files.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from redteam4rag.core.config import ScanConfig


class TestScanConfigDefaults:
    def test_loads_with_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        cfg = ScanConfig()
        assert cfg.judge_provider == "anthropic"
        assert cfg.judge_model == "claude-sonnet-4-6"
        assert cfg.generator_provider == "anthropic"
        assert cfg.generator_model == "claude-haiku-4-5-20251001"
        assert cfg.concurrency == 5
        assert cfg.retry == 2
        assert cfg.mutation_strategy == "static"
        assert cfg.mutation_count == 0
        assert cfg.dry_run is False
        assert cfg.include_trace is False
        assert cfg.attacks_config == "quick"
        assert cfg.fail_on == "high"

    def test_optional_secrets_default_to_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        cfg = ScanConfig()
        assert cfg.target_token is None
        assert cfg.target_api_key is None
        assert cfg.openai_api_key is None


class TestScanConfigSecrets:
    def test_api_key_not_in_repr(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-super-secret")
        cfg = ScanConfig()
        assert "sk-super-secret" not in repr(cfg)

    def test_api_key_not_in_str(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-super-secret")
        cfg = ScanConfig()
        assert "sk-super-secret" not in str(cfg)

    def test_api_key_not_in_model_dump(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-super-secret")
        cfg = ScanConfig()
        dumped = str(cfg.model_dump())
        assert "sk-super-secret" not in dumped

    def test_secret_value_accessible_explicitly(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-real-value")
        cfg = ScanConfig()
        assert cfg.anthropic_api_key.get_secret_value() == "sk-real-value"

    def test_target_token_secret_hidden_in_repr(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        cfg = ScanConfig(target_token="bearer-secret-token")  # type: ignore[arg-type]
        assert "bearer-secret-token" not in repr(cfg)


class TestScanConfigEnvFile:
    def test_loads_api_key_from_env_file(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-from-dotenv\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = ScanConfig()
        assert cfg.anthropic_api_key.get_secret_value() == "sk-from-dotenv"

    def test_env_var_takes_precedence_over_env_file(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-from-file\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
        cfg = ScanConfig()
        assert cfg.anthropic_api_key.get_secret_value() == "sk-from-env"


class TestScanConfigValidation:
    def test_missing_api_key_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)   # no .env file here
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises((ValidationError, Exception)):
            ScanConfig()

    def test_constructor_overrides_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-base")
        cfg = ScanConfig(concurrency=10, judge_provider="openai")
        assert cfg.concurrency == 10
        assert cfg.judge_provider == "openai"

    def test_judge_model_override(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        cfg = ScanConfig(judge_model="claude-opus-4-7")
        assert cfg.judge_model == "claude-opus-4-7"

    def test_generator_provider_independent_of_judge(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
        cfg = ScanConfig(judge_provider="openai", judge_model="gpt-4o",
                         generator_provider="anthropic", generator_model="claude-haiku-4-5-20251001")
        assert cfg.judge_provider == "openai"
        assert cfg.judge_model == "gpt-4o"
        assert cfg.generator_provider == "anthropic"
        assert cfg.generator_model == "claude-haiku-4-5-20251001"

    def test_generator_model_override(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        cfg = ScanConfig(generator_provider="openai", generator_model="gpt-4o-mini")
        assert cfg.generator_provider == "openai"
        assert cfg.generator_model == "gpt-4o-mini"

    def test_openai_api_key_secret_hidden(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        cfg = ScanConfig(openai_api_key="sk-oai-secret")  # type: ignore[arg-type]
        assert "sk-oai-secret" not in repr(cfg)
        assert cfg.openai_api_key.get_secret_value() == "sk-oai-secret"

    def test_mutation_fields(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        cfg = ScanConfig(mutation_strategy="llm", mutation_count=3)
        assert cfg.mutation_strategy == "llm"
        assert cfg.mutation_count == 3

    def test_include_trace_flag(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        cfg = ScanConfig(include_trace=True)
        assert cfg.include_trace is True
