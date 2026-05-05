"""
tests/unit/test_http_adapter.py

Unit tests for HTTPAdapter using respx to mock httpx.
All tests run without network access.
"""

from __future__ import annotations

import os

import httpx
import pytest
import respx

from redteam4rag.adapters.http import HTTPAdapter
from redteam4rag.core.config import ScanConfig
from redteam4rag.models import Probe

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TARGET_URL = "http://fakerag.local/query"
HEALTH_URL = "http://fakerag.local/health"


@pytest.fixture(autouse=True)
def set_api_key(monkeypatch):
    """Inject a fake Anthropic API key so ScanConfig validates successfully."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")


def make_config(**kwargs) -> ScanConfig:
    """Build a ScanConfig with test defaults; caller may override via kwargs."""
    defaults = dict(
        anthropic_api_key="sk-ant-test",
        target_url=TARGET_URL,
        retry=2,
        timeout_seconds=5.0,
    )
    defaults.update(kwargs)
    return ScanConfig.model_validate(defaults)


def make_adapter(config: ScanConfig | None = None, selector_config: dict | None = None) -> HTTPAdapter:
    cfg = config or make_config()
    return HTTPAdapter(cfg, selector_config or {})


PROBE = Probe(query="What is RAG?")

# ---------------------------------------------------------------------------
# Full 200 response: all selectors extract correct values
# ---------------------------------------------------------------------------

FULL_RESPONSE_BODY = {
    "answer": "RAG is retrieval-augmented generation.",
    "chunks": ["Chunk A", "Chunk B"],
    "chunk_details": [
        {
            "text": "Chunk A detail",
            "doc_id": "doc1",
            "namespace": "ns1",
            "score": 0.95,
            "reranker_score": 0.80,
            "position": 0,
            "source_uri": "s3://bucket/doc1.txt",
        }
    ],
    "retrieval_query": "RAG definition",
    "cache": {"hit": True, "key": "abc123", "age_seconds": 42.0},
    "trace": {
        "assembled_prompt": "You are helpful…",
        "reasoning_steps": ["step1", "step2"],
        "tool_calls": [{"name": "search"}],
        "rewrite_steps": ["original query"],
        "token_usage": {"prompt": 100, "completion": 50},
    },
    "debug": {"internal": "data"},
}

SELECTOR_CONFIG = {
    "response_selector": "$.answer",
    "chunk_selector": "$.chunks[*]",
    "chunk_detail_selector": "$.chunk_details[*]",
    "retrieval_query_selector": "$.retrieval_query",
    "cache_selector": "$.cache",
    "trace_selector": "$.trace",
    "debug_selector": "$.debug",
}


@respx.mock
async def test_200_all_selectors():
    """All JSONPath selectors extract correct values from a rich 200 response."""
    respx.post(TARGET_URL).mock(return_value=httpx.Response(200, json=FULL_RESPONSE_BODY))

    adapter = make_adapter(selector_config=SELECTOR_CONFIG)
    raw = await adapter.query(PROBE)

    assert raw.status_code == 200
    assert raw.response_text == "RAG is retrieval-augmented generation."

    assert raw.retrieved_chunks == ["Chunk A", "Chunk B"]

    assert len(raw.chunk_details) == 1
    cd = raw.chunk_details[0]
    assert cd.text == "Chunk A detail"
    assert cd.doc_id == "doc1"
    assert cd.namespace == "ns1"
    assert cd.score == 0.95
    assert cd.reranker_score == 0.80
    assert cd.position == 0
    assert cd.source_uri == "s3://bucket/doc1.txt"

    assert raw.retrieval_query == "RAG definition"

    assert raw.cache_info is not None
    assert raw.cache_info.hit is True
    assert raw.cache_info.key == "abc123"
    assert raw.cache_info.age_seconds == 42.0

    assert raw.trace is not None
    assert raw.trace.assembled_prompt == "You are helpful…"
    assert raw.trace.reasoning_steps == ["step1", "step2"]
    assert raw.trace.tool_calls == [{"name": "search"}]
    assert raw.trace.rewrite_steps == ["original query"]
    assert raw.trace.token_usage == {"prompt": 100, "completion": 50}

    assert raw.debug_payload == {"internal": "data"}

# ---------------------------------------------------------------------------
# trace_selector path missing → trace is None, no exception
# ---------------------------------------------------------------------------

@respx.mock
async def test_trace_selector_missing_from_response():
    """When the trace path is absent, RawResponse.trace is None without raising."""
    body = {"answer": "hello", "chunks": []}
    respx.post(TARGET_URL).mock(return_value=httpx.Response(200, json=body))

    adapter = make_adapter(selector_config={"trace_selector": "$.trace"})
    raw = await adapter.query(PROBE)

    assert raw.trace is None

# ---------------------------------------------------------------------------
# trace_selector present with partial fields → absent LLMTrace fields are None
# ---------------------------------------------------------------------------

@respx.mock
async def test_trace_partial_fields():
    """LLMTrace fields absent in the response dict are None."""
    body = {
        "answer": "ok",
        "chunks": [],
        "trace": {"assembled_prompt": "hello"},
    }
    respx.post(TARGET_URL).mock(return_value=httpx.Response(200, json=body))

    adapter = make_adapter(selector_config={"trace_selector": "$.trace"})
    raw = await adapter.query(PROBE)

    assert raw.trace is not None
    assert raw.trace.assembled_prompt == "hello"
    assert raw.trace.reasoning_steps is None
    assert raw.trace.tool_calls is None
    assert raw.trace.rewrite_steps is None
    assert raw.trace.token_usage is None

# ---------------------------------------------------------------------------
# Missing optional selector → field is None, no exception
# ---------------------------------------------------------------------------

@respx.mock
async def test_missing_optional_selector():
    """When an optional selector is not provided, the corresponding field is None."""
    body = {"answer": "fine", "chunks": []}
    respx.post(TARGET_URL).mock(return_value=httpx.Response(200, json=body))

    # No cache_selector, no chunk_detail_selector, no retrieval_query_selector
    adapter = make_adapter(selector_config={
        "response_selector": "$.answer",
        "chunk_selector": "$.chunks[*]",
        # deliberately omitting: cache_selector, chunk_detail_selector,
        #   retrieval_query_selector, trace_selector, debug_selector
        "trace_selector": None,
        "cache_selector": None,
    })
    raw = await adapter.query(PROBE)

    assert raw.cache_info is None
    assert raw.chunk_details == []
    assert raw.retrieval_query is None
    assert raw.trace is None
    assert raw.debug_payload is None

# ---------------------------------------------------------------------------
# 4xx → status_code recorded, response_text fallback, no exception
# ---------------------------------------------------------------------------

@respx.mock
async def test_4xx_response():
    """4xx response is recorded as status_code=404, response_text='', no exception."""
    respx.post(TARGET_URL).mock(return_value=httpx.Response(404, json={"error": "not found"}))

    adapter = make_adapter()
    raw = await adapter.query(PROBE)

    assert raw.status_code == 404
    assert raw.response_text == ""
    # body parsed from JSON
    assert raw.body == {"error": "not found"}

# ---------------------------------------------------------------------------
# 5xx → retried up to config.retry, then returns errored response
# ---------------------------------------------------------------------------

@respx.mock
async def test_5xx_retried_then_error(monkeypatch):
    """5xx triggers retries; after all attempts, returns an errored RawResponse."""
    # Patch _async_sleep to be instant
    import redteam4rag.adapters.http as http_mod
    monkeypatch.setattr(http_mod, "_async_sleep", _instant_sleep)

    config = make_config(retry=2)  # 1 initial + 2 retries = 3 total attempts
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": "server error"})

    respx.post(TARGET_URL).mock(side_effect=side_effect)

    adapter = make_adapter(config=config)
    raw = await adapter.query(PROBE)

    assert raw.status_code == 500
    assert call_count == 3  # initial + 2 retries

# ---------------------------------------------------------------------------
# Auth: Bearer token header present
# ---------------------------------------------------------------------------

@respx.mock
async def test_auth_bearer_token():
    """Authorization: Bearer <token> header is sent when target_token is set."""
    config = make_config(target_token="my-secret-token")
    received_headers: dict = {}

    def capture(request):
        received_headers.update(dict(request.headers))
        return httpx.Response(200, json={"answer": "ok", "chunks": []})

    respx.post(TARGET_URL).mock(side_effect=capture)

    adapter = make_adapter(config=config)
    await adapter.query(PROBE)

    assert received_headers.get("authorization") == "Bearer my-secret-token"

# ---------------------------------------------------------------------------
# Auth: X-Api-Key header present
# ---------------------------------------------------------------------------

@respx.mock
async def test_auth_api_key():
    """X-Api-Key header is sent when target_api_key is set."""
    config = make_config(target_api_key="apikey-abc")
    received_headers: dict = {}

    def capture(request):
        received_headers.update(dict(request.headers))
        return httpx.Response(200, json={"answer": "ok", "chunks": []})

    respx.post(TARGET_URL).mock(side_effect=capture)

    adapter = make_adapter(config=config)
    await adapter.query(PROBE)

    assert received_headers.get("x-api-key") == "apikey-abc"

# ---------------------------------------------------------------------------
# health_check() returns True on 200, False on non-200
# ---------------------------------------------------------------------------

@respx.mock
async def test_health_check_true():
    """health_check() returns True when /health responds 200."""
    respx.get(HEALTH_URL).mock(return_value=httpx.Response(200))

    adapter = make_adapter()
    result = await adapter.health_check()

    assert result is True


@respx.mock
async def test_health_check_false():
    """health_check() returns False when /health responds non-200."""
    respx.get(HEALTH_URL).mock(return_value=httpx.Response(503))

    adapter = make_adapter()
    result = await adapter.health_check()

    assert result is False

# ---------------------------------------------------------------------------
# latency_ms is a positive float
# ---------------------------------------------------------------------------

@respx.mock
async def test_latency_ms_positive():
    """latency_ms is a positive float after a successful query."""
    respx.post(TARGET_URL).mock(return_value=httpx.Response(200, json={"answer": "hi", "chunks": []}))

    adapter = make_adapter()
    raw = await adapter.query(PROBE)

    assert isinstance(raw.latency_ms, float)
    assert raw.latency_ms >= 0.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _instant_sleep(_seconds: float) -> None:
    """No-op replacement for _async_sleep to skip delays in tests."""
