"""
redteam4rag/core/config.py

ScanConfig — unified config object loaded via pydantic-settings.
Precedence: CLI flags > .redteam4rag.yaml > env vars > .env file > built-in defaults.
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScanConfig(BaseSettings):
    # --- Required secrets ---
    anthropic_api_key: SecretStr
    openai_api_key: SecretStr | None = None   # only needed when a provider is "openai"

    # --- Optional auth ---
    target_token: SecretStr | None = None
    target_api_key: SecretStr | None = None

    # --- Judge LLM ---
    judge_provider: str = "anthropic"        # "anthropic" | "openai" | "ollama"
    judge_model: str = "claude-sonnet-4-6"

    # --- Probe generator LLM (independent of judge) ---
    generator_provider: str = "anthropic"    # "anthropic" | "openai" | "ollama"
    generator_model: str = "claude-haiku-4-5-20251001"

    # --- Scan target & attack config ---
    target_url: str = ""
    attacks_config: str = "quick"   # built-in: quick | full | retriever-only | pii-focused; or path to YAML

    # --- Execution ---
    concurrency: int = 5
    retry: int = 2
    timeout_seconds: float = 30.0
    dry_run: bool = False

    # --- Mutation ---
    mutation_strategy: str = "static"        # "static" | "llm" | "template"
    mutation_count: int = 0

    # --- Output ---
    output_path: str = "report"
    output_format: str = "json"              # "json" | "md" | "html" | "all"
    fail_on: str = "high"                    # minimum Severity to exit 1
    verbose: bool = False
    include_trace: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",           # no prefix: ANTHROPIC_API_KEY → anthropic_api_key
        populate_by_name=True,
        extra="ignore",
    )
