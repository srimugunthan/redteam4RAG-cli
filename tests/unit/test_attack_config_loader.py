"""
tests/unit/test_attack_config_loader.py

Unit tests for AttackConfigLoader — Phase 5.
"""

from __future__ import annotations

import pytest

from redteam4rag.core.attack_config_loader import AttackConfig, AttackConfigLoader, ConfigError
from redteam4rag.models import AttackSpec


class TestBuiltinConfigs:
    def test_quick_returns_12_attacks(self):
        cfg = AttackConfigLoader.load("quick")
        assert isinstance(cfg, AttackConfig)
        assert len(cfg.attacks) == 12

    def test_full_returns_24_attacks(self):
        cfg = AttackConfigLoader.load("full")
        assert isinstance(cfg, AttackConfig)
        assert len(cfg.attacks) == 24

    def test_retriever_only_returns_5_attacks(self):
        cfg = AttackConfigLoader.load("retriever-only")
        assert isinstance(cfg, AttackConfig)
        assert len(cfg.attacks) == 5

    def test_pii_focused_returns_6_attacks(self):
        cfg = AttackConfigLoader.load("pii-focused")
        assert isinstance(cfg, AttackConfig)
        assert len(cfg.attacks) == 6

    def test_all_returned_items_are_attack_spec_instances(self):
        cfg = AttackConfigLoader.load("full")
        for item in cfg.attacks:
            assert isinstance(item, AttackSpec)

    def test_quick_attack_config_attributes(self):
        cfg = AttackConfigLoader.load("quick")
        assert cfg.name == "quick"
        assert cfg.generator == "static"
        assert cfg.judge == "regex"
        assert cfg.concurrency == 5

    def test_full_attack_config_attributes(self):
        cfg = AttackConfigLoader.load("full")
        assert cfg.name == "full"
        assert cfg.generator == "static"
        assert cfg.judge == "regex"
        assert cfg.concurrency == 5

    def test_retriever_only_config_attributes(self):
        cfg = AttackConfigLoader.load("retriever-only")
        assert cfg.name == "retriever-only"
        assert cfg.generator == "static"
        assert cfg.judge == "regex"
        assert cfg.concurrency == 5

    def test_pii_focused_config_attributes(self):
        cfg = AttackConfigLoader.load("pii-focused")
        assert cfg.name == "pii-focused"
        assert cfg.generator == "static"
        assert cfg.judge == "regex"
        assert cfg.concurrency == 5

    def test_full_covers_all_5_categories(self):
        """Verify full config has attacks from each of the 5 categories."""
        from redteam4rag.models import AttackCategory
        cfg = AttackConfigLoader.load("full")
        categories = {spec.category for spec in cfg.attacks}
        assert AttackCategory.RETRIEVER in categories
        assert AttackCategory.CONTEXT in categories
        assert AttackCategory.INJECTION in categories
        assert AttackCategory.DATA_LEAKAGE in categories
        assert AttackCategory.FAITHFULNESS in categories


class TestUnknownBuiltinName:
    def test_unknown_builtin_name_raises_config_error(self):
        with pytest.raises(ConfigError):
            AttackConfigLoader.load("nonexistent-config")

    def test_unknown_builtin_name_error_describes_problem(self):
        with pytest.raises(ConfigError, match="nonexistent-config"):
            AttackConfigLoader.load("nonexistent-config")


class TestCustomYaml:
    def test_custom_yaml_loads_correctly(self, tmp_path):
        yaml_file = tmp_path / "custom.yaml"
        yaml_file.write_text(
            "name: custom-test\n"
            "generator: static\n"
            "judge: regex\n"
            "concurrency: 3\n"
            "attacks:\n"
            "  - empty-retrieval-probe\n"
            "  - pii-exfiltration\n"
        )
        cfg = AttackConfigLoader.load(str(yaml_file))
        assert cfg.name == "custom-test"
        assert cfg.concurrency == 3
        assert len(cfg.attacks) == 2
        attack_names = [spec.name for spec in cfg.attacks]
        assert "empty-retrieval-probe" in attack_names
        assert "pii-exfiltration" in attack_names

    def test_unknown_attack_name_in_custom_yaml_raises_config_error(self, tmp_path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(
            "name: bad\n"
            "attacks:\n"
            "  - nonexistent-attack-xyzzy\n"
        )
        with pytest.raises(ConfigError, match="nonexistent-attack-xyzzy"):
            AttackConfigLoader.load(str(yaml_file))

    def test_per_attack_generator_override_propagates(self, tmp_path):
        yaml_file = tmp_path / "override.yaml"
        yaml_file.write_text(
            "name: override-test\n"
            "generator: static\n"
            "judge: regex\n"
            "concurrency: 1\n"
            "attacks:\n"
            "  - name: query-drift\n"
            "    generator: llm:claude-sonnet-4-6\n"
            "  - keyword-injection\n"
        )
        cfg = AttackConfigLoader.load(str(yaml_file))
        assert len(cfg.attacks) == 2
        drift_spec = next(s for s in cfg.attacks if s.name == "query-drift")
        assert drift_spec.generator_override == "llm:claude-sonnet-4-6"
        # The plain string entry should not have a generator_override
        keyword_spec = next(s for s in cfg.attacks if s.name == "keyword-injection")
        # keyword-injection's generator_override should be whatever was registered
        # (None by default unless the module sets it)
        assert keyword_spec.generator_override is None
