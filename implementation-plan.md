# Implementation Plan — RedTeam4RAG v1.0

**Based on:** system-design.md  
**Date:** April 2026

---

## Dependency Graph

Each phase must complete before the phases that depend on it can start.
Phases on the same row with no arrows between them can run in parallel.

```
Phase 0  ──────────────────────────────────────────────────────────────────
Test RAG Server (DONE)

Phase 1  ──────────────────────────────────────────────────────────────────
Data Models + Config  (foundation for everything)

Phase 2A                          Phase 2B
HTTP Adapter          ────────    Judge Layer
(needs Ph.1)          parallel   (needs Ph.1)

Phase 3A                          Phase 3B
Attack Registry +     ─────────   Report Builder
Probe Generators                  (needs Ph.1 only)
(needs Ph.2A + 2B)    parallel

Phase 4  (needs Ph.3A)
Attack Modules  ── 5 categories written in parallel ──────────────────────
  Retriever (5)   Context (5)   Injection (5)   Leakage (4)   Faith (5)

Phase 5  (needs Ph.4)
Suite Loader

Phase 6  (needs Ph.5 + Ph.3B)
Orchestrator

Phase 7  (needs Ph.6)
CLI Layer

Phase 8  (needs Ph.7 + Ph.0)
End-to-End Tests
```

**Critical path:** Ph.1 → Ph.2A → Ph.3A → Ph.4 → Ph.5 → Ph.6 → Ph.7 → Ph.8  
**Parallel savings:** Ph.2B and Ph.3B can be built concurrently with the critical path.

---

## Phase 0 — Test RAG Server ✅ COMPLETE

**Files:** `test_rag/__init__.py`, `test_rag/server.py`

Already implemented. Provides the live target for all subsequent phases.

### What it gives you
- `POST /query` — full Response Contract (answer, chunks, cache, debug)
- `GET/POST/DELETE /corpus` — runtime corpus manipulation for poisoning tests
- `POST /cache/clear` — cache reset between test runs
- 12 pre-loaded corpus documents covering every v1.0 attack scenario
- Configurable vulnerability flags: `namespace_isolation`, `follow_injections`, `use_cache`

### How to run
```bash
pip install fastapi uvicorn
uvicorn test_rag.server:app --port 8000 --reload
curl http://localhost:8000/health
# {"status":"ok","corpus_size":12}
```

### Phase complete when
- `GET /health` returns 200
- `POST /query` with `{"query": "refund policy"}` returns all Response Contract fields
- `POST /corpus` accepts a new document and it becomes retrievable

---

## Phase 1 — Data Models & Config

**Files:**
- `redteam4rag/models.py` — all frozen dataclasses
- `redteam4rag/core/config.py` — ScanConfig

**Depends on:** nothing  
**Parallel with:** nothing (everything depends on this)

### What to build

All Pydantic v2 dataclasses from system-design §4:

```python
Probe, ChunkDetail, CacheInfo, RawResponse,
JudgeContext, JudgeVerdict,
AttackSpec, AttackResult, ScanResult, ScanMetadata, ScanSummary
```

`ScanConfig` via `pydantic-settings`:

```python
class ScanConfig(BaseSettings):
    anthropic_api_key: SecretStr
    target_token:      SecretStr | None = None
    target_api_key:    SecretStr | None = None
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

### Tests (zero external calls, zero network)
- All dataclasses instantiate without error
- Frozen dataclasses reject mutation
- `SecretStr` fields do not appear in `repr()`, `str()`, or `.model_dump()`
- `ScanConfig` loads `ANTHROPIC_API_KEY` from a temp `.env` file
- Missing required fields raise `ValidationError` at construction time

### Phase complete when
```bash
pytest tests/unit/test_models.py tests/unit/test_config.py -v
# All pass, no network calls
```

---

## Phase 2A — HTTP Adapter

**Files:**
- `redteam4rag/adapters/base.py` — `TargetAdapter` Protocol
- `redteam4rag/adapters/http.py` — `HTTPAdapter`

**Depends on:** Phase 1  
**Parallel with:** Phase 2B (Judge Layer)

### What to build

- `TargetAdapter` Protocol with `query(probe) -> RawResponse` and `health_check() -> bool`
- `HTTPAdapter` using `httpx.AsyncClient`:
  - Jinja2 request template rendering
  - Bearer / API key auth header injection
  - JSONPath selector extraction for all Response Contract fields:
    `response_selector`, `chunk_selector`, `chunk_detail_selector`,
    `retrieval_query_selector`, `cache_selector`, `debug_selector`
  - Retry with exponential backoff (`--retry`, default 2)
  - Latency measurement → `RawResponse.latency_ms`

### Tests (uses `respx` to mock HTTP — no live server needed yet)
- 200 response: all JSONPath selectors extract correct values into `RawResponse`
- Missing optional selector: field is `None`, no exception
- 4xx / 5xx: recorded as `status: errored`, not raised
- Timeout: retried up to `--retry` limit, then `errored`
- Auth: `Authorization: Bearer <token>` header present when `target_token` set
- `health_check()` returns `True` on 200, `False` on non-200

### Phase complete when
```bash
pytest tests/unit/test_http_adapter.py -v
# All pass using respx mocks
```

---

## Phase 2B — Judge Layer  *(parallel with Phase 2A)*

**Files:**
- `redteam4rag/judges/base.py` — `BaseJudge`, `JudgeContext`, `JudgeVerdict`
- `redteam4rag/judges/registry.py` — `JudgeRegistry`
- `redteam4rag/judges/regex.py` — `RegexJudge`
- `redteam4rag/judges/llm.py` — `LLMJudge`
- `redteam4rag/judges/compound.py` — `CompoundJudge`

**Depends on:** Phase 1  
**Parallel with:** Phase 2A

### What to build

`BaseJudge` abstract base with `async def judge(ctx: JudgeContext) -> JudgeVerdict`.

| Judge | Key behaviour |
|---|---|
| `RegexJudge` | Compile pattern at init; `match_means: pass\|fail` controls polarity; applied to `response_text` |
| `LLMJudge` | Jinja2 prompt template (`judge_prompt.txt.j2`); parse `PASS`/`FAIL` + reasoning from Claude response; graceful fallback on malformed output |
| `CompoundJudge` | Takes `list[BaseJudge]` + combiner (`and_` / `or_`); short-circuit evaluation |

### Tests (LLM calls mocked with `unittest.mock`)
- `RegexJudge`: match → FAIL (when `match_means: fail`); no match → PASS; inverse polarity
- `LLMJudge`: mocked Anthropic returns "PASS" string → `JudgeVerdict(passed=True)`; "FAIL" → False; garbled response → fallback verdict with `confidence=None`
- `CompoundJudge` AND: both pass → PASS; one fail → FAIL
- `CompoundJudge` OR: one pass → PASS; both fail → FAIL
- `JudgeRegistry` resolves `"llm:claude-sonnet-4-6"` and `"regex"` to correct class

### Phase complete when
```bash
pytest tests/unit/test_judges.py -v
# All pass, Anthropic client mocked
```

---

## Phase 3A — Attack Registry & Probe Generators

**Files:**
- `redteam4rag/attacks/registry.py` — `AttackRegistry`, `@attack` decorator
- `redteam4rag/generators/base.py` — `ProbeGenerator` Protocol, `ProbeGeneratorFactory`
- `redteam4rag/generators/static.py` — `StaticProbeGenerator`
- `redteam4rag/generators/llm.py` — `LLMProbeGenerator`

**Depends on:** Phase 2A, Phase 2B  
**Parallel with:** Phase 3B (Report Builder)

### What to build

**AttackRegistry:**
- Module-level `dict[str, AttackSpec]`
- `@attack(name, category, severity, tags)` decorator that calls `registry.register(spec)` at import
- `RegistryError` on duplicate name

**StaticProbeGenerator:**
- Expand `spec.queries` as Jinja2 templates
- If `spec.dataset` is set, load JSONL and produce one `Probe` per row × query
- No LLM calls, no network

**LLMProbeGenerator:**
- Call `claude-haiku-4-5` with structured prompt (system-design §3.6)
- Use `spec.queries` as few-shot seeds
- Return `spec.n_probes` `Probe` objects
- Store generated queries in probe metadata for replay

**ProbeGeneratorFactory.create(spec, config):**
- Resolve: `spec.generator_override` > suite generator > `"static"`

### Tests
- `StaticProbeGenerator`: single query → one probe; Jinja2 template + JSONL 3 rows → 3 probes; missing variable → `TemplateError`
- `LLMProbeGenerator`: mocked Anthropic returns 5 query lines → 5 probes; each probe has `attack_name` set
- `ProbeGeneratorFactory`: `"static"` → `StaticProbeGenerator`; `"llm:claude-haiku-4-5"` → `LLMProbeGenerator`
- `AttackRegistry`: duplicate name raises `RegistryError`; unknown name raises `KeyError`

### Phase complete when
```bash
pytest tests/unit/test_registry.py tests/unit/test_generators.py -v
```

---

## Phase 3B — Report Builder  *(parallel with Phase 3A)*

**Files:**
- `redteam4rag/reports/builder.py` — `ReportBuilder` facade
- `redteam4rag/reports/json_writer.py` — `JSONReportWriter`
- `redteam4rag/reports/markdown_writer.py` — `MarkdownReportWriter`
- `redteam4rag/reports/html_writer.py` — `HTMLReportWriter`
- `redteam4rag/templates/report.md.j2`
- `redteam4rag/templates/report.html.j2`

**Depends on:** Phase 1 only  
**Parallel with:** Phase 3A

### What to build

All writers accept `ScanResult`, return `str`. No I/O inside writers.

**JSONReportWriter:** `ScanResult.model_dump_json(indent=2)`  
**MarkdownReportWriter:** Jinja2 template — summary table + per-finding detail blocks  
**HTMLReportWriter:** Jinja2 template — self-contained (all CSS/JS inline):
- Colour-coded severity badge counts at top
- Findings table sortable by severity
- Each finding row expands via `<details>`/`<summary>` to show query, chunks, response, judge reasoning
- No external asset references (no CDN links)

`ReportBuilder.write(result, path, format)`:
- `format="json"` → writes `.json`
- `format="md"` → writes `.md`
- `format="html"` → writes `.html`
- `format="all"` → writes all three

### Tests (no network, no file system — writers return strings)
- `JSONReportWriter`: output parses as valid JSON; all required schema fields present; `SecretStr` fields absent
- `MarkdownReportWriter`: output contains expected headings; finding count matches `ScanResult`
- `HTMLReportWriter`: no `http://` or `https://` in output (self-contained); each finding has a `<details>` element; severity badge counts match summary
- `ReportBuilder` with `format="all"`: produces three files with correct extensions

### Phase complete when
```bash
pytest tests/unit/test_reports.py -v
```

---

## Phase 4 — Attack Modules  *(5 categories in parallel)*

**Files:** 24 attack modules under `redteam4rag/attacks/`

**Depends on:** Phase 3A (registry + generators)  
**Parallel within phase:** all 5 categories are independent of each other

Each attack module:
1. Defines `queries: list[str]` (static seeds or Jinja2 templates)
2. Calls `@attack(name=..., category=..., severity=..., tags=[...])` decorator
3. Optionally sets `judge_override` or `generator_override` on the spec

### Category assignments (can be parallelised across contributors)

| Track | Files | Key corpus docs used |
|---|---|---|
| **Retriever** | `retriever/query_drift.py`, `embedding_inversion.py`, `keyword_injection.py`, `sparse_dense_mismatch.py`, `empty_retrieval_probe.py` | All standard docs |
| **Context** | `context/context_stuffing.py`, `conflicting_chunk_injection.py`, `distractor_document.py`, `position_bias_probe.py`, `long_context_dilution.py` | `policy-refund-conflict`, `stats-corrupted-001` |
| **Injection** | `injection/direct_prompt_injection.py`, `indirect_prompt_injection.py`, `role_confusion.py`, `instruction_override.py`, `system_prompt_extraction.py` | `injected-malicious-001`, `admin-override-001` |
| **Data Leakage** | `data_leakage/pii_exfiltration.py`, `cross_user_isolation.py`, `membership_inference.py`, `verbatim_extraction.py` | `internal-user-records`, `tenant-beta-secret-001` |
| **Faithfulness** | `faithfulness/hallucination_under_ambiguity.py`, `source_misattribution.py`, `sycophancy_override.py`, `refusal_bypass.py`, `temporal_confusion.py` | `news-outdated-2020` |

### Tests — live test_rag server required for this phase

Each attack module gets an integration test that:
1. Starts `test_rag/server.py` (pytest fixture, `uvicorn` in subprocess)
2. Sends the attack's static probes via `HTTPAdapter`
3. Applies the attack's judge
4. Asserts the **expected outcome**: attacks targeting the server's intentionally vulnerable behaviours must return `FAILED`; attacks against hardened behaviours must return `PASSED`

| Attack | Expected result against test_rag (defaults) |
|---|---|
| `indirect-prompt-injection` | FAILED (`follow_injections=true`) |
| `instruction-override` | FAILED |
| `pii-exfiltration` | FAILED (SSN in corpus) |
| `cross-user-isolation` | PASSED (isolation on by default) |
| `temporal-confusion` | FAILED (2020 news doc present) |
| `conflicting-chunk-injection` | FAILED |
| `empty-retrieval-probe` | PASSED (server admits ignorance) |
| ... | ... |

### Phase complete when
```bash
pytest tests/integration/test_attacks/ -v --live-rag
# All 24 attack integration tests pass
```

---

## Phase 5 — Suite Loader

**Files:**
- `redteam4rag/core/suite_loader.py` — `SuiteLoader`
- `redteam4rag/suites/quick.yaml`
- `redteam4rag/suites/full.yaml`
- `redteam4rag/suites/retriever-only.yaml`
- `redteam4rag/suites/pii-focused.yaml`

**Depends on:** Phase 4 (all attack modules registered)

### What to build

`SuiteLoader.load(name_or_path) -> Suite`:
- Accepts a built-in suite name (`"quick"`, `"full"`) or a path to a custom YAML file
- Resolves each attack name against `AttackRegistry`
- Raises `ConfigError` (with the unknown name) on first unresolved attack — fail-fast before any requests
- Returns `Suite(name, generator, judge, concurrency, attacks: list[AttackSpec])`

**quick.yaml** — 12 highest-impact attacks (the 12 listed in system-design §3.4)  
**full.yaml** — all 24 attacks  
**retriever-only.yaml** — RET-001 through RET-005  
**pii-focused.yaml** — LEAK-001 through LEAK-004 + INJ-002, INJ-004

### Tests
- `load("quick")` returns 12 `AttackSpec` objects
- `load("full")` returns 24 `AttackSpec` objects
- Unknown attack name raises `ConfigError` containing the bad name
- Custom YAML path loads correctly
- Per-attack `generator_override` in YAML propagates to `AttackSpec`

### Phase complete when
```bash
pytest tests/unit/test_suite_loader.py -v
```

---

## Phase 6 — Orchestrator

**Files:**
- `redteam4rag/core/orchestrator.py`
- `redteam4rag/core/scheduler.py`

**Depends on:** Phase 5 (Suite Loader), Phase 3B (Report Builder)

### What to build

```python
class Orchestrator:
    async def run(self, config: ScanConfig) -> ScanResult:
        suite = SuiteLoader.load(config.suite)
        adapter = TargetAdapterFactory.create(config)
        semaphore = asyncio.Semaphore(config.concurrency)

        async def run_one(spec: AttackSpec) -> AttackResult:
            async with semaphore:
                generator = ProbeGeneratorFactory.create(spec, config)
                probes = await generator.generate(spec)
                results = []
                for probe in probes:
                    raw = await adapter.query(probe)
                    verdict = await JudgeRegistry.judge(spec, raw, config)
                    results.append(build_attack_result(spec, probe, raw, verdict))
                return merge_attack_results(results)

        tasks = [run_one(s) for s in suite.attacks]
        attack_results = await asyncio.gather(*tasks, return_exceptions=False)
        return ScanResult(config=config, results=attack_results)
```

Also:
- Rich `Progress` bar updated after each attack completes
- `--dry-run`: run `health_check()` only, then exit 0
- `sys.exit(1)` if any finding at or above `--fail-on` severity

### Tests — live test_rag server

- Full orchestrator run with `quick` suite against test_rag: `ScanResult` contains 12 `AttackResult` objects
- `concurrency=1` and `concurrency=5` both complete without deadlock
- An errored attack (test_rag returns 500 for one probe) does not crash the scan; other attacks complete
- `--dry-run` makes zero `/query` calls (tracked via a counter on the mock)
- `--fail-on high` sets `sys.exit` code to 1 when a high finding exists

### Phase complete when
```bash
pytest tests/integration/test_orchestrator.py -v --live-rag
# Full scan completes, ScanResult structure correct
```

---

## Phase 7 — CLI Layer

**Files:**
- `redteam4rag/cli/main.py`
- `redteam4rag/cli/scan.py`
- `redteam4rag/cli/corpus.py`
- `redteam4rag/cli/plugin.py`
- `redteam4rag/cli/report.py`
- `pyproject.toml` — entry point `redteam4rag = "redteam4rag.cli.main:app"`

**Depends on:** Phase 6 (Orchestrator)

### What to build

Typer app wiring all subcommands:

| Subcommand | Delegates to |
|---|---|
| `scan` | `Orchestrator.run()` → `ReportBuilder.write()` |
| `corpus inspect` | `GET /corpus` on target → formatted table |
| `plugin list` | `AttackRegistry` + `JudgeRegistry` → formatted table |
| `report reformat` | `ReportBuilder.write()` on existing JSON |
| `version` | Print version string from `importlib.metadata` |

Config merging: CLI flags override `.redteam4rag.yaml` values which override built-in defaults, all via `pydantic-settings`.

### Tests (typer.testing.CliRunner — no live server needed)
- `redteam4rag version` → exits 0, prints version string
- `redteam4rag scan` with no `--target` → exits 2, prints usage
- `redteam4rag scan --dry-run --target http://localhost:8000/query` → exits 0
- `redteam4rag scan --suite unknown-suite` → exits 2, prints `ConfigError` message
- `redteam4rag plugin list` → exits 0, lists all 24 registered attacks
- `--verbose` flag causes request/response to appear in output
- `--output report.json --format all` produces `.json`, `.md`, `.html` files

### Phase complete when
```bash
pytest tests/unit/test_cli.py -v
# All CliRunner tests pass without live server
```

---

## Phase 8 — End-to-End Tests

**Files:**
- `tests/e2e/test_e2e_scan.py`
- `.redteam4rag.yaml` (project config pointing at test_rag)

**Depends on:** Phase 7 (CLI), Phase 0 (Test RAG server running)

### Full end-to-end scenarios

**Scenario 1 — Quick scan, regex judge (zero API cost)**
```bash
uvicorn test_rag.server:app --port 8000 &
redteam4rag scan \
  --target http://localhost:8000/query \
  --suite quick \
  --judge regex \
  --output ./reports/quick_scan \
  --format all
```
Assert:
- Exit code 1 (injection + PII findings above threshold)
- `quick_scan.json` is valid JSON matching the published schema
- `quick_scan.html` is self-contained (no external URLs)
- `quick_scan.md` contains a summary table

**Scenario 2 — Full scan, LLM judge**
```bash
redteam4rag scan \
  --target http://localhost:8000/query \
  --suite full \
  --judge llm:claude-sonnet-4-6 \
  --output ./reports/full_scan.json \
  --fail-on high
```
Assert:
- Exit code 1
- All 24 attacks produce a result (none stuck in `errored`)
- Known-vulnerable attacks (`indirect-prompt-injection`, `pii-exfiltration`, `temporal-confusion`) appear as `FAILED`
- `internal-user-records` namespace chunk appears in evidence for `pii-exfiltration`

**Scenario 3 — Hardened server (injections disabled)**
```bash
# Start server with follow_injections=false default by patching the default in the request
redteam4rag scan \
  --target http://localhost:8000/query \
  --suite quick \
  --judge regex
```
Assert:
- `indirect-prompt-injection` returns `PASSED` (server hardened)
- Exit code 0 if no other high findings

**Scenario 4 — Dry run**
```bash
redteam4rag scan \
  --target http://localhost:8000/query \
  --suite full \
  --dry-run
```
Assert:
- Exit code 0
- Zero requests to `/query` (health check only)
- Output says "Dry run complete"

**Scenario 5 — Custom suite YAML**
```bash
redteam4rag scan \
  --target http://localhost:8000/query \
  --suite ./my_suite.yaml \
  --output report.json
```
Assert: only attacks named in `my_suite.yaml` appear in report.

### Phase complete when
```bash
pytest tests/e2e/test_e2e_scan.py -v --live-rag
# All 5 scenarios pass
echo "v1.0 implementation complete"
```

---

## Parallel Execution Summary

```
Week 1:   [Phase 0 ✅]  [Phase 1 ───────────]
Week 2:   [Phase 2A ────────]  [Phase 2B ────────]  (parallel)
Week 3:   [Phase 3A ────────]  [Phase 3B ────────]  (parallel)
Week 4-5: [Phase 4: Retriever][Context ][Injection][Leakage][Faith]  (parallel)
Week 6:   [Phase 5 ─────────────────────────────]
Week 7:   [Phase 6 ─────────────────────────────]
Week 8:   [Phase 7 ─────────────────────────────]
Week 9:   [Phase 8 ─────────────────────────────]
```

With 2 engineers splitting the parallel phases: ~7 weeks to E2E.  
With 1 engineer sequential: ~9 weeks to E2E.

---

## Test Fixtures

Every phase from Phase 4 onward needs the test_rag server running. Use a `pytest` session-scoped fixture:

```python
# tests/conftest.py
import subprocess, time, pytest, httpx

@pytest.fixture(scope="session")
def live_rag_server():
    proc = subprocess.Popen(
        ["uvicorn", "test_rag.server:app", "--port", "8000"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # wait for server to be ready
    for _ in range(20):
        try:
            httpx.get("http://localhost:8000/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    yield "http://localhost:8000"
    proc.terminate()
```

Run live tests with:
```bash
pytest --live-rag   # uses the fixture
pytest              # skips live tests (unit + mocked only)
```

---

## Definition of Done per Phase

| Phase | Done signal |
|---|---|
| 0 | `/health` returns 200, corpus_size=12 |
| 1 | `pytest tests/unit/test_models.py tests/unit/test_config.py` green |
| 2A | `pytest tests/unit/test_http_adapter.py` green (respx mocks) |
| 2B | `pytest tests/unit/test_judges.py` green (Anthropic mocked) |
| 3A | `pytest tests/unit/test_registry.py tests/unit/test_generators.py` green |
| 3B | `pytest tests/unit/test_reports.py` green |
| 4 | `pytest tests/integration/test_attacks/ --live-rag` green — all 24 attacks produce expected PASS/FAIL |
| 5 | `pytest tests/unit/test_suite_loader.py` green |
| 6 | `pytest tests/integration/test_orchestrator.py --live-rag` green |
| 7 | `pytest tests/unit/test_cli.py` green (CliRunner, no live server) |
| 8 | `pytest tests/e2e/ --live-rag` green — full CLI scan produces valid JSON + HTML + MD reports |
