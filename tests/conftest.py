"""
tests/conftest.py

Session-scoped fixtures and CLI options shared across all test tiers.
Live-server tests are skipped unless --live-rag is passed.
"""

from __future__ import annotations

import subprocess
import time

import httpx
import pytest


@pytest.fixture(scope="session")
def live_rag_server():
    proc = subprocess.Popen(
        ["uvicorn", "test_rag.server:app", "--port", "8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        try:
            httpx.get("http://localhost:8000/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    yield "http://localhost:8000"
    proc.terminate()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live-rag",
        action="store_true",
        default=False,
        help="Run integration and e2e tests that require a live test_rag server",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--live-rag"):
        skip = pytest.mark.skip(reason="requires --live-rag flag")
        for item in items:
            if "live_rag_server" in item.fixturenames:
                item.add_marker(skip)
