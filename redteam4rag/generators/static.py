"""
redteam4rag/generators/static.py

StaticProbeGenerator — generates probes from static query templates and
optional JSONL dataset files. No LLM calls, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import jinja2

from redteam4rag.models import AttackSpec, Probe


class StaticProbeGenerator:
    """
    Generates Probe instances from the queries defined in an AttackSpec.

    - If spec.dataset is None: each query string becomes one Probe (rendered
      as a Jinja2 template with no variables).
    - If spec.dataset is set: the JSONL file is loaded and each query template
      is rendered once per row, producing len(queries) × len(rows) probes.
    """

    _jinja_env: jinja2.Environment = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        autoescape=False,
    )

    async def generate(self, spec: AttackSpec) -> list[Probe]:
        """Generate probes from spec.queries, optionally expanded via dataset."""
        probes: list[Probe] = []

        if spec.dataset is None:
            # Simple case: one probe per query, no template variables
            for query in spec.queries:
                rendered = self._render(query, {})
                probes.append(
                    Probe(
                        query=rendered,
                        metadata={"attack_name": spec.name, "source": "static"},
                    )
                )
        else:
            # Dataset case: render each query against each row
            rows = self._load_jsonl(spec.dataset)
            for query in spec.queries:
                for row in rows:
                    rendered = self._render(query, row)
                    probes.append(
                        Probe(
                            query=rendered,
                            metadata={"attack_name": spec.name, "source": "static"},
                        )
                    )

        return probes

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _render(self, template_str: str, variables: dict) -> str:
        """Render a Jinja2 template string with the given variables.

        Raises jinja2.TemplateError if a referenced variable is missing.
        """
        template = self._jinja_env.from_string(template_str)
        return template.render(**variables)

    @staticmethod
    def _load_jsonl(path: str) -> list[dict]:
        """Load a JSONL file, returning a list of dicts (one per line)."""
        rows: list[dict] = []
        p = Path(path)
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
