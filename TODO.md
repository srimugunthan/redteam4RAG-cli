# RedTeam4RAG — Future Work

## Multi-Turn Attack Generation

Single-turn probes cover most attack categories, but several attacks only surface across
multiple conversation turns (session fixation, gradual trust escalation, payload splitting,
memory poisoning). This section documents what needs to change to support them.

### Estimated effort: 3–4 weeks

---

### 1. TargetAdapter — session support

Add two optional methods to the Protocol so adapters can maintain conversation state:

```python
class TargetAdapter(Protocol):
    async def send(self, probe: Probe) -> RawResponse: ...

    # New — optional; raise NotImplementedError if target is stateless
    async def new_session(self) -> str: ...          # returns session_id
    async def end_session(self, session_id: str) -> None: ...
```

`HTTPAdapter` implementation: POST to a `/session` endpoint (or pass a header) and
store the returned session token. `SDKAdapter`: pass a `conversation_id` parameter to
the SDK call.

---

### 2. Probe dataclass — session fields

```python
@dataclass(frozen=True)
class Probe:
    query: str
    attack_name: str
    injected_payload: str | None = None

    # New
    session_id: str | None = None
    conversation_history: list[dict] | None = None  # [{"role": ..., "content": ...}]
    turn_index: int = 0
```

---

### 3. Orchestrator — delegate execution loop

Today the orchestrator owns the probe → send → judge loop. For multi-turn attacks the
attack module must control the loop (it decides when to escalate, when to stop, what to
inject next).

Change: if `spec.run` is not None the orchestrator delegates entirely:

```python
if spec.run is not None:
    result = await spec.run(adapter, context)
else:
    # existing single-turn loop
    probes = await generator.generate(spec)
    ...
```

Single-turn attacks are unaffected (their `run` field stays None).

---

### 4. ProbeGenerator — ConversationScript concept

Add a `ConversationScript` type for multi-turn probe sequences:

```python
@dataclass
class ConversationScript:
    turns: list[str]                              # static turn texts
    dynamic_next: Callable[[list[dict]], Awaitable[str]] | None = None
    # dynamic_next receives conversation_history and returns the next turn text
    # used for LLM-driven escalation strategies
    max_turns: int = 10
    stop_condition: Callable[[RawResponse], bool] | None = None
```

`LLMProbeGenerator` gains a `generate_script()` method alongside its existing
`generate()` method.

---

### 5. JudgeContext and AttackResult — conversation history

```python
@dataclass
class JudgeContext:
    probe: Probe
    response: RawResponse
    conversation_history: list[dict] | None = None   # New

@dataclass
class AttackResult:
    probe: Probe
    response: RawResponse
    passed: bool
    score: float
    reason: str
    conversation_history: list[dict] | None = None   # New
```

LLMJudge prompt template needs a `{% if conversation_history %}` block that prepends
the full transcript so the judge can reason about gradual escalation.

---

### 6. Attack modules to author

Once the framework changes above land, write these multi-turn attack modules:

| Attack ID   | Name                     | Strategy |
|-------------|--------------------------|----------|
| SESSION-001 | Session Fixation         | Inject session token in turn 1, assert privileged access in turn 3 |
| SESSION-002 | Context Window Poisoning | Fill early turns with benign context, inject malicious payload near limit |
| SESSION-003 | Gradual Trust Escalation | Establish helpful persona over 3 turns, then exfiltrate PII |
| SESSION-004 | Memory Poisoning         | Assert false facts in turn 1, query them back in turn 5 |
| SESSION-005 | Conversation Hijacking   | Interleave legit / injection turns to confuse retrieval |
| QUERY-007   | Payload Splitting        | Split injection across 2 turns so per-turn filters miss it |

Each module lives in `attacks/session/SESSION-001.py` etc. and implements the
`run: Callable[[TargetAdapter, AttackContext], Awaitable[AttackResult]]` signature.

---

### Dependencies / prerequisites

- Decide on session API contract with test RAG server (`test_rag/server.py`) before
  writing `HTTPAdapter.new_session()` — the server needs a `/session` endpoint.
- Conversation history schema should follow the Anthropic Messages API format
  (`role` / `content`) so it maps directly to `LLMProbeGenerator` calls without
  conversion.
- Add `multi_turn: true` flag to `AttackSpec` so the CLI can warn when a suite
  targets a stateless adapter.

---

## Post-v1.0 Attack Backlog

74 attacks from `RAG-Attacks_DB.md` not implemented in v1.0. Grouped by category with
the framework prerequisites each batch requires.

### Retrieval Layer (9 attacks)

| ID | Name | Notes |
|----|------|-------|
| RET-006 | Top-K Saturation | Requires corpus write + `chunks[].doc_id` score analysis |
| RET-007 | Adversarial Query Suffix | Needs embedding-aware probe generator |
| RET-008 | Retrieval Query Rewriting Manipulation | Requires `retrieval_query` field in response |
| RET-009 | HyDE Exploitation | Requires `retrieval_query` field; HyDE-specific RAG feature |
| RET-010 | Similarity Threshold Boundary Attack | Requires `chunks[].score` and fine-grained score probing |
| RET-011 | Negative Space Query | LLM judge; black-box capable |
| RET-012 | Cross-Language Retrieval Attack | Requires multilingual probe dataset |
| RET-013 | Reranker Bypass | Requires corpus write + `chunks[].reranker_score` |
| RET-014 | Adversarial Query Prefix | Needs embedding-aware probe generator |

### Context Manipulation (6 attacks)

| ID | Name | Notes |
|----|------|-------|
| CTX-006 | Chunk Boundary Exploitation | Requires understanding of target chunking strategy |
| CTX-007 | Metadata Poisoning | Requires corpus write + `chunks[].source_uri` |
| CTX-008 | Context Window Overflow | Requires large token-count probe dataset |
| CTX-009 | Authority Impersonation in Chunks | Requires corpus write; test fixture exists in `test_rag` |
| CTX-010 | Semantic Decoy | Requires corpus write + EmbeddingJudge (v1.1) |
| CTX-011 | Numeric / Statistical Corruption | Requires corpus write; test fixture exists in `test_rag` |

### Prompt Injection (7 attacks)

| ID | Name | Notes |
|----|------|-------|
| INJ-006 | Multilingual Injection | Requires multilingual probe dataset |
| INJ-007 | Encoded Injection (Base64 / Hex) | Regex judge; straightforward once encoding variants are enumerated |
| INJ-008 | Markdown / HTML Injection | Regex judge; requires output renderer context |
| INJ-009 | Nested Conditional Injection | Requires corpus write + multi-chunk coordination |
| INJ-010 | Persona Injection | Requires corpus write; LLM judge |
| INJ-011 | Jailbreak via Retrieved Authority | Requires corpus write; LLM judge |
| INJ-012 | Reasoning Chain Poisoning | Requires corpus write; LLM judge with chain-of-thought extraction |

### Data Leakage & Privacy (7 attacks)

| ID | Name | Notes |
|----|------|-------|
| LEAK-005 | Document Enumeration | Requires `/corpus` endpoint or equivalent; test RAG exposes this |
| LEAK-006 | Internal Path / URI Leakage | Regex judge on `chunks[].source_uri`; straightforward |
| LEAK-007 | System Configuration Leakage | LLM judge; black-box |
| LEAK-008 | Cross-Tenant Isolation Breach | Variant of LEAK-002 requiring explicit namespace parameter |
| LEAK-009 | Aggregate Inference Attack | Requires multi-query correlation logic in attack module |
| LEAK-010 | Training Data Extraction | LLM + EmbeddingJudge; targets generator memorization not corpus |
| LEAK-011 | Embedding Vector Reconstruction | Requires systematic score-probing across many queries |

### Faithfulness & Generation (5 attacks)

| ID | Name | Notes |
|----|------|-------|
| FAITH-006 | Confidence Inflation | Requires corpus write; LLM judge on hedging language |
| FAITH-007 | Citation Fabrication | LLM judge; black-box capable |
| FAITH-008 | Factual Corruption via Conflicting Authorities | Requires corpus write; test fixture exists in `test_rag` |
| FAITH-009 | Numeric Hallucination | LLM + Regex judge; test fixture exists in `test_rag` |
| FAITH-010 | Refusal Inconsistency Probe | Requires semantically equivalent probe pairs; LLM judge |

### Corpus Poisoning (7 attacks)

| ID | Name | Notes |
|----|------|-------|
| CORP-001 | Direct Corpus Poisoning | Requires corpus write API; `POST /corpus` in test RAG |
| CORP-002 | Semantic Backdoor | Requires corpus write + trigger-phrase probe pairs |
| CORP-003 | Embedding Space Poisoning | Requires corpus write + Score judge + embedding model access |
| CORP-004 | Index Flooding | Requires corpus write; bulk document injection |
| CORP-005 | Adversarial Document Crafting | Requires corpus write + embedding model for optimization |
| CORP-006 | Chunk Fragmentation Exploit | Requires corpus write + knowledge of chunking strategy |
| CORP-007 | Trigger-phrase Backdoor | Requires corpus write + trigger/non-trigger probe pairs |

### Cache & Infrastructure (6 attacks)

| ID | Name | Notes |
|----|------|-------|
| INFRA-001 | Cache Poisoning | Requires `cache.hit` + `cache.key`; Diff judge across two runs |
| INFRA-002 | Cache Timing Side-Channel | Requires Timing judge; measures latency delta |
| INFRA-003 | Prompt Cache Cross-User Leakage | Requires `cache.key`; LLM + Diff judge |
| INFRA-004 | Rate Limit Bypass via Batching | Infrastructure-level; Timing judge |
| INFRA-005 | Vector Store SSRF | Requires corpus write + `debug_payload` SSRF listener |
| INFRA-006 | Embedding API Abuse | Score judge; requires embedding API exposure |

### Adversarial Query Crafting (7 attacks)

| ID | Name | Notes |
|----|------|-------|
| QUERY-001 | Homoglyph / Unicode Substitution | Regex judge; requires Unicode lookalike probe dataset |
| QUERY-002 | Token Smuggling | LLM judge; requires tokenizer-aware probe generator |
| QUERY-003 | Chain-of-Thought Prompt Leaking | LLM + Regex judge; black-box |
| QUERY-004 | Semantic Similarity Bombing | Score judge; requires many similar probes per attack |
| QUERY-005 | Abstract / Oblique Query Attack | LLM judge; black-box |
| QUERY-006 | Negation Retrieval Bypass | LLM judge; black-box |
| QUERY-007 | Payload Splitting Across Turns | Requires multi-turn framework (see Multi-Turn section above) |

### Embedding & Model-Level (4 attacks)

| ID | Name | Notes |
|----|------|-------|
| EMBED-001 | Embedding Model Inversion | Score judge; requires systematic query probing |
| EMBED-002 | Adversarial Embedding Crafting | Requires corpus write + embedding model access |
| EMBED-003 | Embedding Drift Exploitation | Requires knowledge of index-time vs query-time model versions |
| EMBED-004 | Model Extraction via Systematic Queries | Diff + Score judge; requires many structured probes |

### Agentic RAG (7 attacks)

| ID | Name | Notes |
|----|------|-------|
| AGENT-001 | Tool Call Injection via Retrieved Content | Requires agentic RAG with tool-use; `debug_payload` for tool call trace |
| AGENT-002 | Action Hijacking | Requires agentic RAG; LLM judge on planned vs executed action |
| AGENT-003 | Privilege Escalation via Agent Tool | Requires agentic RAG + tool call logging in `debug_payload` |
| AGENT-004 | Data Exfiltration via Agent Tool | Requires agentic RAG + outbound request monitoring |
| AGENT-005 | Agent Loop Injection | Requires agentic RAG; Timing judge for loop detection |
| AGENT-006 | Goal / Objective Hijacking | Requires agentic RAG; LLM judge on goal drift |
| AGENT-007 | Memory Poisoning (Long-term) | Requires multi-turn framework + persistent memory store |

### Multimodal RAG (4 attacks)

| ID | Name | Notes |
|----|------|-------|
| MODAL-001 | Image-Embedded Prompt Injection | Requires multimodal RAG + image corpus write |
| MODAL-002 | OCR Exploitation | Requires multimodal RAG with OCR pipeline + image corpus write |
| MODAL-003 | Audio-Embedded Injection | Requires multimodal RAG with STT pipeline + audio corpus write |
| MODAL-004 | Adversarial Image Embedding | Requires multimodal RAG + image embedding model access |
