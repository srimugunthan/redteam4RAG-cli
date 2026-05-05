"""
redteam4rag/adapters/http.py

HTTPAdapter — sends probes to a RAG endpoint over HTTP using httpx.AsyncClient.
Supports JSONPath-based extraction of response fields, Jinja2 request templating,
Bearer/ApiKey auth injection, and exponential-backoff retry on timeout/5xx.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx
from jinja2 import Template
from jsonpath_ng.ext import parse as jp_parse

from redteam4rag.core.config import ScanConfig
from redteam4rag.models import (
    CacheInfo,
    ChunkDetail,
    LLMTrace,
    Probe,
    RawResponse,
)

# ---------------------------------------------------------------------------
# Default selector expressions
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, str] = {
    "response_selector": "$.answer",
    "chunk_selector": "$.chunks[*]",
    "trace_selector": "$.trace",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_one(expr_str: str | None, data: dict) -> Any:
    """Return the first JSONPath match or None if missing/error."""
    if not expr_str:
        return None
    try:
        matches = jp_parse(expr_str).find(data)
        return matches[0].value if matches else None
    except Exception:
        return None


def _extract_many(expr_str: str | None, data: dict) -> list[Any]:
    """Return all JSONPath matches or [] if missing/error."""
    if not expr_str:
        return []
    try:
        return [m.value for m in jp_parse(expr_str).find(data)]
    except Exception:
        return []


def _build_chunk_detail(raw: Any) -> ChunkDetail | None:
    """Map a dict (or scalar) to ChunkDetail. Returns None on failure."""
    if not isinstance(raw, dict):
        return None
    return ChunkDetail(
        text=raw.get("text", ""),
        doc_id=raw.get("doc_id"),
        namespace=raw.get("namespace"),
        score=raw.get("score"),
        reranker_score=raw.get("reranker_score"),
        position=raw.get("position"),
        source_uri=raw.get("source_uri"),
    )


def _build_llm_trace(raw: Any) -> LLMTrace | None:
    """Map a dict to LLMTrace. Returns None when raw is None or not a dict."""
    if raw is None or not isinstance(raw, dict):
        return None
    return LLMTrace(
        assembled_prompt=raw.get("assembled_prompt"),
        reasoning_steps=raw.get("reasoning_steps"),
        tool_calls=raw.get("tool_calls"),
        rewrite_steps=raw.get("rewrite_steps"),
        token_usage=raw.get("token_usage"),
    )


def _build_cache_info(raw: Any) -> CacheInfo | None:
    """Map a dict to CacheInfo. Returns None when raw is absent."""
    if raw is None or not isinstance(raw, dict):
        return None
    return CacheInfo(
        hit=bool(raw.get("hit", False)),
        key=raw.get("key"),
        age_seconds=raw.get("age_seconds"),
    )


def _base_url(target_url: str) -> str:
    """Strip path/query/fragment to get scheme+host+port only."""
    parsed = urlparse(target_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return base


# ---------------------------------------------------------------------------
# HTTPAdapter
# ---------------------------------------------------------------------------

_DEFAULT_BODY_TEMPLATE = '{"query": "{{ query }}"}'


class HTTPAdapter:
    """Sends Probe objects to a RAG HTTP endpoint and returns RawResponse."""

    def __init__(
        self,
        config: ScanConfig,
        selector_config: dict | None = None,
        body_template: str = _DEFAULT_BODY_TEMPLATE,
    ) -> None:
        self._config = config
        sc = selector_config or {}

        # Merge defaults — caller values win over defaults
        self._response_selector: str | None = sc.get(
            "response_selector", _DEFAULTS["response_selector"]
        )
        self._chunk_selector: str | None = sc.get(
            "chunk_selector", _DEFAULTS["chunk_selector"]
        )
        self._chunk_detail_selector: str | None = sc.get("chunk_detail_selector")
        self._retrieval_query_selector: str | None = sc.get("retrieval_query_selector")
        self._cache_selector: str | None = sc.get("cache_selector")
        self._trace_selector: str | None = sc.get(
            "trace_selector", _DEFAULTS["trace_selector"]
        )
        self._debug_selector: str | None = sc.get("debug_selector")

        self._body_template = Template(body_template)

        # Build headers
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.target_token is not None:
            self._headers["Authorization"] = (
                f"Bearer {config.target_token.get_secret_value()}"
            )
        if config.target_api_key is not None:
            self._headers["X-Api-Key"] = config.target_api_key.get_secret_value()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(self, probe: Probe) -> RawResponse:
        """POST probe to target_url with exponential-backoff retry."""
        body_str = self._body_template.render(
            query=probe.query,
            include_trace=self._config.include_trace,
            **probe.metadata,
        )

        attempt = 0
        max_attempts = 1 + max(0, self._config.retry)  # initial + retries
        delay = 0.5  # seconds, doubles each attempt

        async with httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            headers=self._headers,
        ) as client:
            while attempt < max_attempts:
                t0 = time.perf_counter()
                try:
                    response = await client.post(
                        self._config.target_url,
                        content=body_str,
                    )
                    latency_ms = (time.perf_counter() - t0) * 1000.0

                    status_code = response.status_code

                    # On 5xx, retry if attempts remain
                    if response.is_server_error and attempt < max_attempts - 1:
                        attempt += 1
                        await _async_sleep(delay)
                        delay *= 2
                        continue

                    # Parse body (best-effort)
                    try:
                        body: dict = response.json()
                    except Exception:
                        body = {}

                    if response.is_success:
                        return self._build_raw_response(
                            status_code=status_code,
                            body=body,
                            latency_ms=latency_ms,
                        )
                    else:
                        # 4xx or non-retried 5xx
                        return RawResponse(
                            status_code=status_code,
                            body=body,
                            response_text="",
                            latency_ms=latency_ms,
                        )

                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    if attempt < max_attempts - 1:
                        attempt += 1
                        await _async_sleep(delay)
                        delay *= 2
                        continue
                    # Exhausted retries on timeout
                    return RawResponse(
                        status_code=None,
                        body={},
                        response_text="",
                        latency_ms=latency_ms,
                    )

                attempt += 1

        # Fallback (should not reach here)
        return RawResponse(status_code=None, body={}, response_text="")

    async def health_check(self) -> bool:
        """GET {base_url}/health — returns True on 200, False otherwise."""
        base = _base_url(self._config.target_url)
        url = f"{base}/health"
        try:
            async with httpx.AsyncClient(timeout=5.0, headers=self._headers) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_raw_response(
        self,
        status_code: int,
        body: dict,
        latency_ms: float,
    ) -> RawResponse:
        response_text: str = _extract_one(self._response_selector, body) or ""

        # Chunks as plain strings
        retrieved_chunks: list[str] = [
            str(v) for v in _extract_many(self._chunk_selector, body)
        ]

        # Detailed chunk objects
        raw_chunk_details = _extract_many(self._chunk_detail_selector, body)
        chunk_details: list[ChunkDetail] = [
            cd
            for raw in raw_chunk_details
            if (cd := _build_chunk_detail(raw)) is not None
        ]

        retrieval_query: str | None = _extract_one(
            self._retrieval_query_selector, body
        )

        raw_cache = _extract_one(self._cache_selector, body)
        cache_info = _build_cache_info(raw_cache)

        raw_trace = _extract_one(self._trace_selector, body)
        trace = _build_llm_trace(raw_trace)

        raw_debug = _extract_one(self._debug_selector, body)
        debug_payload: dict | None = raw_debug if isinstance(raw_debug, dict) else None

        return RawResponse(
            status_code=status_code,
            body=body,
            response_text=response_text,
            retrieved_chunks=retrieved_chunks,
            chunk_details=chunk_details,
            retrieval_query=retrieval_query,
            cache_info=cache_info,
            latency_ms=latency_ms,
            trace=trace,
            debug_payload=debug_payload,
        )


# ---------------------------------------------------------------------------
# asyncio sleep shim — avoids importing asyncio at module level
# ---------------------------------------------------------------------------

async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
