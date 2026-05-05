"""
redteam4rag/models.py

All core data models. Plain Python dataclasses (no Pydantic overhead on hot paths).
Frozen where immutability is important; mutable only for result aggregates built
incrementally during a scan run.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AttackStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"


class AttackCategory(str, Enum):
    RETRIEVER = "retriever"
    CONTEXT = "context"
    INJECTION = "injection"
    DATA_LEAKAGE = "data_leakage"
    FAITHFULNESS = "faithfulness"


# ---------------------------------------------------------------------------
# Execution primitives — frozen for immutability
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Probe:
    query: str
    injected_chunks: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkDetail:
    text: str
    doc_id: str | None = None
    namespace: str | None = None
    score: float | None = None
    reranker_score: float | None = None
    position: int | None = None
    source_uri: str | None = None


@dataclass(frozen=True)
class CacheInfo:
    hit: bool
    key: str | None = None
    age_seconds: float | None = None


@dataclass(frozen=True)
class LLMTrace:
    """
    Optional execution trace emitted by the RAG system.
    All fields are optional — a RAG system may populate any subset.
    When present, LLMJudge includes trace fields in its prompt.
    """
    assembled_prompt: str | None = None
    reasoning_steps: list[str] | None = None
    tool_calls: list[dict] | None = None
    rewrite_steps: list[str] | None = None
    token_usage: dict | None = None


# ---------------------------------------------------------------------------
# Adapter ↔ Judge boundary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RawResponse:
    status_code: int | None
    body: dict
    response_text: str
    retrieved_chunks: list[str] = field(default_factory=list)
    chunk_details: list[ChunkDetail] = field(default_factory=list)
    retrieval_query: str | None = None
    cache_info: CacheInfo | None = None
    latency_ms: float = 0.0
    trace: LLMTrace | None = None
    debug_payload: dict | None = None


@dataclass(frozen=True)
class JudgeContext:
    query: str
    retrieved_chunks: list[str]
    response: str
    attack_metadata: dict
    chunk_details: list[ChunkDetail] = field(default_factory=list)
    retrieval_query: str | None = None
    cache_info: CacheInfo | None = None
    trace: LLMTrace | None = None
    debug_payload: dict | None = None


@dataclass(frozen=True)
class JudgeVerdict:
    passed: bool
    reasoning: str
    confidence: float | None = None
    judge_name: str = ""


# ---------------------------------------------------------------------------
# Attack specification — frozen, registered at import time
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AttackSpec:
    name: str
    category: AttackCategory
    severity: Severity
    tags: frozenset[str]
    queries: tuple[str, ...]          # tuple for hashability; callers pass list or tuple
    dataset: str | None = None        # path to JSONL file for template variables
    judge_override: str | None = None
    generator_override: str | None = None
    n_probes: int = 5

    def __post_init__(self) -> None:
        if isinstance(self.queries, list):
            object.__setattr__(self, "queries", tuple(self.queries))
        if isinstance(self.tags, (list, set)):
            object.__setattr__(self, "tags", frozenset(self.tags))


# ---------------------------------------------------------------------------
# Result aggregates — mutable, built up during a scan
# ---------------------------------------------------------------------------

@dataclass
class AttackResult:
    id: str
    attack_name: str
    category: str
    severity: Severity
    status: AttackStatus
    query: str
    retrieved_chunks: list[str]
    response: str
    judge_verdict: JudgeVerdict | None
    evidence: dict
    latency_ms: float
    error: str | None = None

    @staticmethod
    def make_id() -> str:
        return str(uuid.uuid4())


@dataclass
class ScanMetadata:
    scan_id: str
    target_url: str
    suite_name: str
    judge: str
    generator: str
    started_at: str          # ISO-8601
    finished_at: str         # ISO-8601
    duration_seconds: float
    redteam4rag_version: str = "1.0.0"


@dataclass
class ScanSummary:
    total: int
    passed: int
    failed: int
    errored: int
    by_severity: dict[str, int]    # Severity.value → count of FAILED results
    by_category: dict[str, int]    # AttackCategory.value → count of FAILED results


@dataclass
class ScanResult:
    metadata: ScanMetadata
    results: list[AttackResult]

    @property
    def summary(self) -> ScanSummary:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == AttackStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == AttackStatus.FAILED)
        errored = sum(1 for r in self.results if r.status == AttackStatus.ERRORED)

        by_severity: Counter[str] = Counter()
        by_category: Counter[str] = Counter()
        for r in self.results:
            if r.status == AttackStatus.FAILED:
                by_severity[r.severity.value] += 1
                by_category[r.category] += 1

        return ScanSummary(
            total=total,
            passed=passed,
            failed=failed,
            errored=errored,
            by_severity=dict(by_severity),
            by_category=dict(by_category),
        )
