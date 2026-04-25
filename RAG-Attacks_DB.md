# RAG Attacks Database

**Version:** 1.1  
**Date:** April 2026  
**Purpose:** Comprehensive taxonomy of known RAG attack vectors. Source for selecting the implementation backlog.

---

## Column Definitions

| Column | Meaning |
|---|---|
| **ID** | Stable identifier for referencing in suites and issues |
| **Attack Name** | Human-readable name |
| **Attack Description** | One-line summary of what the attack does |
| **Category** | Top-level attack family |
| **Severity** | Critical / High / Medium / Low — impact if attack succeeds |
| **Attack Vector** | How the attack is delivered: `Query` (crafted user input), `Corpus` (adversarial document pre-loaded), `Session` (multi-turn exploitation), `Infra` (system-level) |
| **Corpus Write Required** | Whether the attacker must control documents in the index |
| **Response Fields Needed** | Fields from the RAG Response Contract (§10, system-design.md) needed for reliable detection |
| **Detection Method** | Primary judge type: `LLM`, `Regex`, `Score`, `Diff`, `Timing` |
| **In v1.0 Plan** | Already planned in system-design.md directory structure |

---

## Category 1 — Retrieval Layer Attacks

Attacks that manipulate *which* documents are retrieved, exploiting the embedding model, similarity scoring, or retrieval algorithm.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| RET-001 | Query Drift | Crafts semantically shifted queries to surface unintended but topically adjacent documents. | High | Query | No | `chunks[].text`, `chunks[].score` | LLM | Yes |
| RET-002 | Embedding Inversion | Issues queries that collide with target document embeddings to reconstruct or surface sensitive indexed content. | Critical | Query | No | `chunks[].text`, `chunks[].doc_id` | LLM + Score | Yes |
| RET-003 | Keyword Injection (BM25) | Injects high-TF-IDF terms into the query to force sparse retrieval to rank a target document first. | High | Query | No | `chunks[].text`, `retrieval_query` | Regex | Yes |
| RET-004 | Sparse-Dense Mismatch Exploitation | Exploits scoring disagreement between BM25 and vector retrieval to surface documents neither system would rank highly alone. | Medium | Query | No | `chunks[].score`, `chunks[].reranker_score` | Score | Yes |
| RET-005 | Empty Retrieval Probe | Sends queries guaranteed to return no chunks to test whether the generator hallucinates or admits ignorance. | Medium | Query | No | `chunks[].text` | Regex | Yes |
| RET-006 | Top-K Saturation | Pre-loads many near-identical adversarial documents to occupy all top-k retrieval slots for a target query. | High | Corpus | Yes | `chunks[].doc_id`, `chunks[].score` | Score | No |
| RET-007 | Adversarial Query Suffix | Appends adversarial text to the query to shift its embedding toward a target region in the vector space. | High | Query | No | `chunks[].text`, `retrieval_query` | LLM + Regex | No |
| RET-008 | Retrieval Query Rewriting Manipulation | Injects instructions that cause the RAG's internal query rewriter to produce a different, attacker-controlled retrieval query. | High | Query | No | `retrieval_query` | LLM | No |
| RET-009 | HyDE Exploitation | Exploits Hypothetical Document Embedding by crafting queries whose hypothetical answer steers retrieval toward unintended documents. | Medium | Query | No | `retrieval_query`, `chunks[].text` | LLM | No |
| RET-010 | Similarity Threshold Boundary Attack | Crafts queries whose embedding sits just above the similarity cutoff, forcing marginal adversarial documents into context. | Medium | Query | No | `chunks[].score` | Score | No |
| RET-011 | Negative Space Query | Uses negation or absence framing to retrieve documents about topics the system is designed to restrict. | Medium | Query | No | `chunks[].text`, `answer` | LLM | No |
| RET-012 | Cross-Language Retrieval Attack | Queries in a different language to retrieve documents indexed in that language, bypassing monolingual content filters. | High | Query | No | `chunks[].text`, `chunks[].source_uri` | LLM | No |
| RET-013 | Reranker Bypass | Pre-loads corpus documents crafted to score high on the cross-encoder reranker despite low initial embedding similarity. | High | Corpus | Yes | `chunks[].score`, `chunks[].reranker_score` | Score | No |
| RET-014 | Adversarial Query Prefix | Prepends adversarial text to the query to shift its embedding and redirect retrieval toward target documents. | High | Query | No | `retrieval_query`, `chunks[].text` | LLM | No |

---

## Category 2 — Context Manipulation Attacks

Attacks that corrupt *how* retrieved chunks are assembled or interpreted in the context window.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| CTX-001 | Context Stuffing | Floods the context window with irrelevant but plausible documents to dilute legitimate information and degrade answer quality. | High | Query | No | `chunks[].text`, `answer` | LLM | Yes |
| CTX-002 | Conflicting Chunk Injection | Injects a corpus document containing facts that contradict legitimate chunks to test whether the generator sides with the attacker's content. | Critical | Corpus | Yes | `chunks[].text`, `answer` | LLM | Yes |
| CTX-003 | Distractor Document | Introduces a topically adjacent but factually misleading document to test whether the generator incorrectly incorporates it. | High | Corpus | Yes | `chunks[].text`, `answer` | LLM | Yes |
| CTX-004 | Position Bias Probe | Tests whether the generator gives undue weight to chunks at the beginning or end of the context window regardless of relevance. | Medium | Query | No | `chunks[].position`, `answer` | LLM | Yes |
| CTX-005 | Long-Context Dilution | Places the answer-bearing chunk far from position 0 among many filler chunks to test the generator's positional sensitivity. | High | Query | No | `chunks[].position`, `answer` | LLM | Yes |
| CTX-006 | Chunk Boundary Exploitation | Splits an adversarial payload across two consecutive chunks so that neither chunk alone triggers detection filters. | High | Corpus | Yes | `chunks[].text` | LLM | No |
| CTX-007 | Metadata Poisoning | Corrupts chunk metadata fields (source URI, author, date) to mislead source attribution in the generated answer. | Medium | Corpus | Yes | `chunks[].source_uri`, `chunks[].doc_id`, `answer` | LLM | No |
| CTX-008 | Context Window Overflow | Sends enough retrieved context to overflow the model's context window, truncating the system prompt or safety instructions. | High | Query | No | `chunks[].text`, `answer` | LLM | No |
| CTX-009 | Authority Impersonation in Chunks | Embeds phrases like "Admin override:" or "Per legal team:" in corpus documents to lend false authority to adversarial instructions. | High | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| CTX-010 | Semantic Decoy | Places a semantically plausible but factually wrong chunk adjacent to the genuine answer chunk, causing the generator to blend incorrect facts. | High | Corpus | Yes | `chunks[].text`, `answer` | LLM + Embedding | No |
| CTX-011 | Numeric / Statistical Corruption | Injects corpus documents containing false numbers or statistics that the generator incorporates verbatim into its answer. | High | Corpus | Yes | `chunks[].text`, `answer` | LLM + Regex | No |

---

## Category 3 — Prompt Injection Attacks

Attacks that hijack the LLM's instruction-following via the query or retrieved content.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| INJ-001 | Direct Prompt Injection | Embeds instruction-hijacking text directly in the user query to override the system prompt or change the model's behavior. | High | Query | No | `answer` | LLM + Regex | Yes |
| INJ-002 | Indirect Prompt Injection | Hides adversarial instructions inside a corpus document that the RAG retrieves and feeds to the generator. | Critical | Corpus | Yes | `chunks[].text`, `answer` | LLM + Regex | Yes |
| INJ-003 | Role Confusion | Crafts queries that convince the LLM it is a different system or persona with different permissions than its system prompt defines. | High | Query | No | `answer` | LLM | Yes |
| INJ-004 | Instruction Override | Places "IGNORE PREVIOUS INSTRUCTIONS"-style payloads in a retrieved document to supersede the system prompt. | Critical | Corpus | Yes | `chunks[].text`, `answer` | Regex | Yes |
| INJ-005 | System Prompt Extraction | Crafts queries designed to elicit verbatim reproduction of the hidden system prompt. | High | Query | No | `answer` | LLM + Regex | Yes |
| INJ-006 | Multilingual Injection | Delivers injection instructions in a different language than the system language to bypass monolingual content filters. | High | Query / Corpus | No | `chunks[].text`, `answer` | LLM | No |
| INJ-007 | Encoded Injection (Base64 / Hex) | Encodes adversarial instructions in Base64, hex, or ROT13 to evade string-matching injection filters. | High | Query / Corpus | No | `chunks[].text`, `answer` | Regex + LLM | No |
| INJ-008 | Markdown / HTML Injection | Uses Markdown or HTML formatting characters to hide instructions or inject rendering-time behavior in the output. | Medium | Corpus | Yes | `chunks[].text`, `answer` | Regex | No |
| INJ-009 | Nested Conditional Injection | Embeds an injection that activates only when combined with content from a second retrieved chunk, evading single-chunk scanning. | High | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| INJ-010 | Persona Injection | Uses retrieved document content to convince the generator to adopt an attacker-defined persona with different behavioral constraints. | High | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| INJ-011 | Jailbreak via Retrieved Authority | Retrieves a corpus document posing as an "official policy override" to justify generating otherwise-refused content. | Critical | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| INJ-012 | Reasoning Chain Poisoning | Injects false premises into retrieved context that corrupt a multi-step reasoning chain, producing a wrong but confidently stated conclusion. | High | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |

---

## Category 4 — Data Leakage & Privacy Attacks

Attacks that extract sensitive information from the corpus or system configuration.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| LEAK-001 | PII Exfiltration via Retrieval | Crafts queries designed to surface chunks containing personally identifiable information from the corpus. | Critical | Query | No | `chunks[].text`, `answer` | Regex + LLM | Yes |
| LEAK-002 | Cross-User Isolation Breach | Simulates multi-tenant leakage by querying data that belongs to a different user's namespace. | Critical | Query | No | `chunks[].namespace`, `chunks[].doc_id` | Score + LLM | Yes |
| LEAK-003 | Membership Inference | Determines whether a specific document is indexed by observing suspiciously high similarity scores for probe queries. | High | Query | No | `chunks[].score`, `answer` | Score | Yes |
| LEAK-004 | Verbatim Extraction | Prompts the generator to reproduce exact text from indexed documents, bypassing paraphrase-based confidentiality protections. | High | Query | No | `chunks[].text`, `answer` | Regex + Embedding | Yes |
| LEAK-005 | Document Enumeration | Systematically queries to enumerate document IDs and source URIs, mapping the structure of the knowledge base. | High | Query | No | `chunks[].doc_id`, `chunks[].source_uri` | LLM + Diff | No |
| LEAK-006 | Internal Path / URI Leakage | Extracts internal file paths, S3 keys, or database IDs from chunk source metadata exposed in the response. | Medium | Query | No | `chunks[].source_uri`, `answer` | Regex | No |
| LEAK-007 | System Configuration Leakage | Elicits disclosure of the model name, temperature, system prompt, or runtime configuration through indirect questioning. | High | Query | No | `answer` | LLM + Regex | No |
| LEAK-008 | Cross-Tenant Isolation Breach | In a multi-tenant RAG, accesses documents from another tenant's namespace by exploiting missing namespace filtering. | Critical | Query | No | `chunks[].namespace` | Score | No |
| LEAK-009 | Aggregate Inference Attack | Combines partial leaks across separate queries to reconstruct a sensitive document that no single query fully reveals. | High | Query | No | `chunks[].text`, `answer` | LLM | No |
| LEAK-010 | Training Data Extraction | Exploits the generator's memorization to reproduce verbatim text from its pre-training data rather than the retrieval corpus. | High | Query | No | `answer` | LLM + Embedding | No |
| LEAK-011 | Embedding Vector Reconstruction | Infers the embedding vector of a target document from similarity score patterns observed across many crafted probe queries. | High | Query | No | `chunks[].score` | Score | No |

---

## Category 5 — Faithfulness & Generation Attacks

Attacks that cause the generator to hallucinate, misattribute, or contradict its retrieved context.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| FAITH-001 | Hallucination Under Ambiguity | Sends queries where retrieved chunks are insufficient to test whether the generator fabricates an answer rather than admitting uncertainty. | High | Query | No | `chunks[].text`, `answer` | LLM | Yes |
| FAITH-002 | Source Misattribution | Tests whether the generator correctly attributes claims to the source chunk or incorrectly cites a different or non-existent source. | Medium | Query | No | `chunks[].source_uri`, `answer` | LLM | Yes |
| FAITH-003 | Sycophancy Override | Includes a false assertion in the user query to test whether the generator capitulates to the user's framing over contradicting retrieved evidence. | High | Query | No | `chunks[].text`, `answer` | LLM | Yes |
| FAITH-004 | Refusal Bypass | Uses adversarial rephrasing or retrieved "authoritative" content to circumvent the model's content-policy refusals. | Critical | Query / Corpus | No | `answer` | LLM + Regex | Yes |
| FAITH-005 | Temporal Confusion | Queries time-sensitive facts where the corpus is stale, testing whether the generator presents outdated information as current. | Low | Query | No | `chunks[].text`, `answer` | LLM | Yes |
| FAITH-006 | Confidence Inflation | Injects corpus documents with overstated certainty ("It is definitively proven that…") to make the generator express false confidence. | Medium | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| FAITH-007 | Citation Fabrication | Crafts queries that lead the generator to invent citations for sources that do not exist in the corpus. | High | Query | No | `chunks[].source_uri`, `answer` | LLM | No |
| FAITH-008 | Factual Corruption via Conflicting Authorities | Presents two retrieved chunks from different "authoritative" sources that contradict each other, causing the generator to blend or arbitrarily choose the wrong fact. | High | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| FAITH-009 | Numeric Hallucination | Crafts ambiguous queries about quantities where retrieved chunks are insufficient, testing whether the generator invents plausible-sounding numbers. | High | Query | No | `chunks[].text`, `answer` | LLM + Regex | No |
| FAITH-010 | Refusal Inconsistency Probe | Sends semantically equivalent queries with different surface forms to detect inconsistent refusal behavior in the generator. | Medium | Query | No | `answer` | LLM | No |

---

## Category 6 — Corpus Poisoning Attacks

Attacks where the adversary plants documents in the knowledge base before retrieval occurs.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| CORP-001 | Direct Corpus Poisoning | Injects plainly adversarial documents into the vector store to test whether retrieval and generation guardrails catch them. | Critical | Corpus | Yes | `chunks[].text`, `chunks[].doc_id` | LLM | No |
| CORP-002 | Semantic Backdoor | Plants documents that appear benign in normal use but activate adversarial behavior when a specific trigger phrase appears in the query. | Critical | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| CORP-003 | Embedding Space Poisoning | Crafts documents whose embeddings cluster near unrelated sensitive queries to hijack retrieval for those queries. | Critical | Corpus | Yes | `chunks[].score`, `chunks[].text` | Score + LLM | No |
| CORP-004 | Index Flooding | Uploads many near-duplicate low-quality documents to dilute legitimate results and push genuine answers below the top-k threshold. | High | Corpus | Yes | `chunks[].doc_id`, `chunks[].score` | Score | No |
| CORP-005 | Adversarial Document Crafting | Constructs documents computationally optimized to maximize retrieval likelihood for a target query while containing an adversarial payload. | High | Corpus | Yes | `chunks[].text`, `chunks[].score` | LLM + Score | No |
| CORP-006 | Chunk Fragmentation Exploit | Exploits the RAG's chunking strategy to split an adversarial payload so that each individual chunk appears harmless to per-chunk scanners. | High | Corpus | Yes | `chunks[].text` | LLM | No |
| CORP-007 | Trigger-phrase Backdoor | Plants a document whose adversarial instruction only executes when a specific rare trigger phrase appears in the user query. | Critical | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |

---

## Category 7 — Cache & Infrastructure Attacks

Attacks that exploit caching, rate-limiting, or system-level components rather than the retrieval/generation pipeline directly.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| INFRA-001 | Cache Poisoning | Gets a malicious response stored in the query cache so all subsequent users issuing the same query receive the poisoned answer. | High | Query | No | `cache.hit`, `cache.key`, `answer` | Diff | No |
| INFRA-002 | Cache Timing Side-Channel | Measures response latency to infer cache hit/miss status, reconstructing which queries other users have previously issued. | Medium | Query | No | `cache.hit`, `cache.age_seconds` | Timing | No |
| INFRA-003 | Prompt Cache Cross-User Leakage | Exploits shared prompt caching to infer another user's session context via cache hit patterns on crafted queries. | High | Query | No | `cache.key`, `answer` | LLM + Diff | No |
| INFRA-004 | Rate Limit Bypass via Batching | Abuses batch API endpoints or parallel requests to exceed per-query rate limits and send more probes than the system intends to allow. | Medium | Infra | No | — | Timing | No |
| INFRA-005 | Vector Store SSRF | Crafts document metadata that causes the vector store client to make unintended outbound network requests to attacker-controlled infrastructure. | Critical | Corpus | Yes | `debug_payload` | LLM + Regex | No |
| INFRA-006 | Embedding API Abuse | Sends adversarial or resource-exhausting inputs to the embedding API to degrade retrieval quality or infer model internals. | Medium | Query | No | `chunks[].score` | Score | No |

---

## Category 8 — Multi-turn & Session Attacks

Attacks that exploit conversation history, session state, or multi-turn context accumulation.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| SESSION-001 | Conversation History Poisoning | Injects adversarial content into stored conversation history to influence the model's behavior in all subsequent turns. | High | Session | No | `answer` | LLM | No |
| SESSION-002 | Context Accumulation Attack | Gradually injects a partial adversarial payload across multiple innocuous turns, completing the injection in a final turn that triggers the combined effect. | High | Session | No | `chunks[].text`, `answer` | LLM | No |
| SESSION-003 | Session State Confusion | Exploits shared or improperly isolated session state to cause the RAG to mix context or retrieval namespaces between different users. | High | Infra | No | `chunks[].namespace` | LLM | No |
| SESSION-004 | Delayed Multi-turn Injection | Spreads an injection payload across several turns so no individual turn triggers detection, completing the attack only in a final combining turn. | Critical | Session | No | `answer` | LLM | No |
| SESSION-005 | Retrieval History Exploitation | Uses knowledge of which documents were retrieved in prior turns to craft a follow-up query that targets a specific vulnerable chunk. | High | Session | No | `chunks[].doc_id`, `answer` | LLM | No |

---

## Category 9 — Adversarial Query Crafting

Attacks that exploit encoding, tokenization, or linguistic edge cases to bypass query-level filters.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| QUERY-001 | Homoglyph / Unicode Substitution | Replaces ASCII characters with visually identical Unicode lookalikes to bypass keyword-based injection or content filters. | High | Query | No | `retrieval_query`, `answer` | Regex | No |
| QUERY-002 | Token Smuggling | Exploits tokenization edge cases (token boundaries, rare characters) to deliver a payload that reads differently to a filter than to the model. | High | Query | No | `retrieval_query`, `answer` | LLM | No |
| QUERY-003 | Chain-of-Thought Prompt Leaking | Uses chain-of-thought instructions in the query to make the model externalize internal reasoning, exposing system prompt or retrieved context details. | High | Query | No | `answer` | LLM + Regex | No |
| QUERY-004 | Semantic Similarity Bombing | Floods the retrieval system with many semantically similar queries to saturate the top-k result set with attacker-chosen documents. | Medium | Query | No | `chunks[].score` | Score | No |
| QUERY-005 | Abstract / Oblique Query Attack | Uses indirect or abstract phrasing to retrieve sensitive documents without triggering keyword-based access controls. | Medium | Query | No | `chunks[].text`, `answer` | LLM | No |
| QUERY-006 | Negation Retrieval Bypass | Frames a query using negation ("What is not allowed?") to retrieve restricted policy documents that affirmative queries would not surface. | Medium | Query | No | `chunks[].text`, `answer` | LLM | No |
| QUERY-007 | Payload Splitting Across Turns | Splits a single adversarial query across multiple turns so each individual message appears benign to per-message filters. | High | Session | No | `answer` | LLM | No |

---

## Category 10 — Embedding & Model-Level Attacks

Attacks targeting the embedding model itself or the representation space.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| EMBED-001 | Embedding Model Inversion | Infers the original text of a corpus document by systematically observing how similarity scores change across crafted probe queries. | High | Query | No | `chunks[].score`, `answer` | Score + LLM | No |
| EMBED-002 | Adversarial Embedding Crafting | Constructs text with specific embedding properties (near-zero distance to a target vector) to reliably redirect retrieval toward a chosen document. | High | Corpus | Yes | `chunks[].score`, `chunks[].text` | Score | No |
| EMBED-003 | Embedding Drift Exploitation | Exploits the difference between the embedding model used at index time and at query time to surface documents that should not rank highly. | Medium | Query | No | `chunks[].score`, `retrieval_query` | Score | No |
| EMBED-004 | Model Extraction via Systematic Queries | Probes the embedding or generation model systematically to infer its parameters or decision boundaries from observed outputs. | High | Query | No | `chunks[].score`, `answer` | Diff + Score | No |

---

## Category 11 — Agentic RAG Attacks

Attacks specific to RAG systems with tool-use or autonomous action capabilities.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| AGENT-001 | Tool Call Injection via Retrieved Content | Embeds tool-call syntax in a corpus document that the agentic RAG interprets as a legitimate tool invocation during generation. | Critical | Corpus | Yes | `chunks[].text`, `answer`, `debug_payload` | LLM + Regex | No |
| AGENT-002 | Action Hijacking | Uses retrieved content to redirect the agent's planned action sequence toward attacker-defined operations. | Critical | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| AGENT-003 | Privilege Escalation via Agent Tool | Triggers a tool call (via injection) that performs operations the original user is not authorized to request. | Critical | Corpus | Yes | `answer`, `debug_payload` | LLM | No |
| AGENT-004 | Data Exfiltration via Agent Tool | Triggers an agent tool call (email, webhook, API) to exfiltrate retrieved sensitive data to an attacker-controlled endpoint. | Critical | Corpus | Yes | `answer`, `debug_payload` | LLM | No |
| AGENT-005 | Agent Loop Injection | Injects a self-referencing or recursive instruction into retrieved content that causes the agent to loop indefinitely, producing a denial of service. | High | Corpus | Yes | `answer`, `debug_payload` | Timing + LLM | No |
| AGENT-006 | Goal / Objective Hijacking | Replaces the agent's original goal with an attacker-defined objective by embedding goal-override instructions in a retrieved document. | Critical | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| AGENT-007 | Memory Poisoning (Long-term) | Corrupts the agent's long-term memory store with false facts or instructions that persist across sessions and influence future interactions. | High | Session | No | `answer` | LLM | No |

---

## Category 12 — Multimodal RAG Attacks

Attacks specific to RAG systems that ingest or retrieve non-text modalities.

| ID | Attack Name | Attack Description | Severity | Attack Vector | Corpus Write | Response Fields Needed | Detection Method | In v1.0 Plan |
|---|---|---|---|---|---|---|---|---|
| MODAL-001 | Image-Embedded Prompt Injection | Hides adversarial text instructions inside an image that the multimodal RAG's vision encoder reads and passes to the generator. | Critical | Corpus | Yes | `chunks[].text`, `answer` | LLM | No |
| MODAL-002 | OCR Exploitation | Crafts an image whose OCR transcription contains an adversarial payload that the RAG pipeline processes as legitimate document text. | High | Corpus | Yes | `chunks[].text`, `answer` | Regex + LLM | No |
| MODAL-003 | Audio-Embedded Injection | Hides adversarial instructions in an audio file that the RAG's speech-to-text component transcribes and feeds to the generator. | High | Corpus | Yes | `answer`, `debug_payload` | LLM | No |
| MODAL-004 | Adversarial Image Embedding | Crafts an image whose embedding vector is close to the embedding of a target text query, hijacking visual retrieval for that query. | High | Corpus | Yes | `chunks[].score` | Score | No |

---

## Summary

| Category | Count | Critical | High | Medium | Low | In v1.0 |
|---|---|---|---|---|---|---|
| Retrieval Layer | 14 | 1 | 8 | 5 | 0 | 5 |
| Context Manipulation | 11 | 1 | 8 | 2 | 0 | 5 |
| Prompt Injection | 12 | 3 | 7 | 2 | 0 | 5 |
| Data Leakage & Privacy | 11 | 3 | 7 | 1 | 0 | 4 |
| Faithfulness & Generation | 10 | 1 | 5 | 3 | 1 | 5 |
| Corpus Poisoning | 7 | 4 | 3 | 0 | 0 | 0 |
| Cache & Infrastructure | 6 | 1 | 3 | 2 | 0 | 0 |
| Multi-turn & Session | 5 | 1 | 4 | 0 | 0 | 0 |
| Adversarial Query Crafting | 7 | 0 | 4 | 3 | 0 | 0 |
| Embedding & Model | 4 | 0 | 3 | 1 | 0 | 0 |
| Agentic RAG | 7 | 5 | 2 | 0 | 0 | 0 |
| Multimodal RAG | 4 | 1 | 3 | 0 | 0 | 0 |
| **Total** | **98** | **21** | **57** | **19** | **1** | **24** |

---

## v1.0 Implementation Selection

24 attacks are implemented in v1.0, covering 5 categories: Retrieval Layer (5), Context Manipulation (5), Prompt Injection (5), Data Leakage & Privacy (4), Faithfulness & Generation (5). These are marked **In v1.0 Plan = Yes** in the tables above.

Selection criteria applied:

1. **Severity** — all 24 are Critical, High, or Medium
2. **Category breadth** — 5 distinct categories catch different vulnerability classes across the full pipeline
3. **Test fixture coverage** — each v1.0 attack has a corresponding corpus document in `test_rag/server.py`
4. **No external model dependency** — all 24 can be detected with `LLM`, `Regex`, or `Score` judges; none require `Timing` or infrastructure access
5. **Corpus Write Required = No** preferred — 17 of the 24 work black/grey-box without corpus write access

Remaining 74 attacks are candidates for v1.1 and beyond.
