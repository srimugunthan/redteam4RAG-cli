"""
redteam4rag/core/attack_config_loader.py

AttackConfigLoader — translates a pre-configured name or custom YAML path
into a validated AttackConfig ready for the orchestrator.
"""
from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from pathlib import Path

import yaml

from redteam4rag.attacks.registry import AttackRegistry, RegistryError
from redteam4rag.models import AttackSpec


class ConfigError(Exception):
    """Raised when an attack config is invalid (unknown attack name, bad YAML, etc.)."""


@dataclass
class AttackConfig:
    name: str
    generator: str          # "static" | "llm:<model>"
    judge: str              # "regex" | "llm:<model>"
    concurrency: int
    attacks: list[AttackSpec]


# Maps built-in names to their YAML filenames inside redteam4rag/attack_configs/
_BUILTIN_CONFIGS: dict[str, str] = {
    "quick": "quick.yaml",
    "full": "full.yaml",
    "retriever-only": "retriever-only.yaml",
    "pii-focused": "pii-focused.yaml",
}

# Directory containing the built-in YAML files (sibling to this file's package)
_CONFIGS_DIR = Path(__file__).parent.parent / "attack_configs"


class AttackConfigLoader:
    @staticmethod
    def load(name_or_path: str) -> AttackConfig:
        """
        Load an AttackConfig by built-in name or path to a custom YAML file.

        Built-in names: "quick", "full", "retriever-only", "pii-focused"
        Custom path:    any string ending in .yaml or containing a path separator

        Raises ConfigError on unknown attack names or bad YAML.
        """
        # First, ensure all attack modules are imported so the registry is populated
        AttackConfigLoader._import_all_attacks()

        # Resolve to a YAML path
        if name_or_path in _BUILTIN_CONFIGS:
            yaml_path = _CONFIGS_DIR / _BUILTIN_CONFIGS[name_or_path]
        else:
            yaml_path = Path(name_or_path)
            if not yaml_path.exists():
                raise ConfigError(
                    f"Attack config not found: {name_or_path!r}. "
                    f"Built-in configs: {list(_BUILTIN_CONFIGS.keys())}"
                )

        try:
            raw = yaml.safe_load(yaml_path.read_text())
        except Exception as e:
            raise ConfigError(f"Failed to parse {yaml_path}: {e}") from e

        # Resolve attack names → AttackSpec objects
        attack_specs: list[AttackSpec] = []
        for entry in raw.get("attacks", []):
            if isinstance(entry, str):
                attack_name = entry
                override_generator = None
            elif isinstance(entry, dict):
                attack_name = entry["name"]
                override_generator = entry.get("generator")
            else:
                raise ConfigError(f"Invalid attack entry: {entry!r}")

            try:
                spec = AttackRegistry.get(attack_name)
            except KeyError:
                raise ConfigError(
                    f"Unknown attack {attack_name!r} in config {name_or_path!r}. "
                    f"Check the attack name spelling."
                )

            # Apply per-attack generator override from YAML
            if override_generator is not None:
                spec = AttackSpec(
                    name=spec.name,
                    category=spec.category,
                    severity=spec.severity,
                    tags=spec.tags,
                    queries=spec.queries,
                    dataset=spec.dataset,
                    judge_override=spec.judge_override,
                    generator_override=override_generator,
                    n_probes=spec.n_probes,
                )

            attack_specs.append(spec)

        return AttackConfig(
            name=raw.get("name", name_or_path),
            generator=raw.get("generator", "static"),
            judge=raw.get("judge", "regex"),
            concurrency=raw.get("concurrency", 5),
            attacks=attack_specs,
        )

    @staticmethod
    def _import_all_attacks() -> None:
        """Import all attack modules so they register themselves via @attack."""
        import importlib
        attack_modules = [
            "redteam4rag.attacks.retriever.query_drift",
            "redteam4rag.attacks.retriever.embedding_inversion",
            "redteam4rag.attacks.retriever.keyword_injection",
            "redteam4rag.attacks.retriever.sparse_dense_mismatch",
            "redteam4rag.attacks.retriever.empty_retrieval_probe",
            "redteam4rag.attacks.context.context_stuffing",
            "redteam4rag.attacks.context.conflicting_chunk_injection",
            "redteam4rag.attacks.context.distractor_document",
            "redteam4rag.attacks.context.position_bias_probe",
            "redteam4rag.attacks.context.long_context_dilution",
            "redteam4rag.attacks.injection.direct_prompt_injection",
            "redteam4rag.attacks.injection.indirect_prompt_injection",
            "redteam4rag.attacks.injection.role_confusion",
            "redteam4rag.attacks.injection.instruction_override",
            "redteam4rag.attacks.injection.system_prompt_extraction",
            "redteam4rag.attacks.data_leakage.pii_exfiltration",
            "redteam4rag.attacks.data_leakage.cross_user_isolation",
            "redteam4rag.attacks.data_leakage.membership_inference",
            "redteam4rag.attacks.data_leakage.verbatim_extraction",
            "redteam4rag.attacks.faithfulness.hallucination_under_ambiguity",
            "redteam4rag.attacks.faithfulness.source_misattribution",
            "redteam4rag.attacks.faithfulness.sycophancy_override",
            "redteam4rag.attacks.faithfulness.refusal_bypass",
            "redteam4rag.attacks.faithfulness.temporal_confusion",
        ]
        for module in attack_modules:
            importlib.import_module(module)
