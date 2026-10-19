"""Observability (P4) tests — hermetic, driven through demo mode.

Covers the structured JSON request log emitted by the middleware, the
StatsCollector math, and the /stats aggregation endpoint.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings
from app.core.stats import STATS, StatsCollector

_KEY_VARS = ("SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY")


def test_stats_collector_math() -> None:
    collector = StatsCollector()
    collector.record(method="GET", path="/health", status=200, latency_ms=10.0)
    collector.record(
        method="POST",
        path="/api/ask",
        status=200,
        latency_ms=30.0,
        retrieval_hit=True,
        token_usage={"calls": 1, "input_tokens": 100, "output_tokens": 40},
    )
    collector.record(
        method="POST", path="/api/ask", status=200, latency_ms=20.0, retrieval_hit=False
    )
    snap = collector.snapshot()
    assert snap["requests_total"] == 3
    assert snap["avg_latency_ms"] == 20.0
    assert snap["retrieval_requests"] == 2
    assert snap["retrieval_hits"] == 1
    assert snap["retrieval_hit_rate"] == 0.5
    assert snap["token_usage"] == {"calls": 1, "input_tokens": 100, "output_tokens": 40}
    assert snap["by_path"] == {"GET /health": 1, "POST /api/ask": 2}
    assert snap["uptime_seconds"] >= 0


def test_stats_collector_empty_hit_rate_is_none() -> None:
    assert StatsCollector().snapshot()["retrieval_hit_rate"] is None


@pytest.fixture()
def demo_client(monkeypatch: pytest.MonkeyPatch):
    """TestClient booted in demo mode (no keys, no Postgres)."""
    monkeypatch.setenv("PAWPILOT_DEMO_MODE", "1")
    for var in _KEY_VARS:
        monkeypatch.setenv(var, "")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_middleware_emits_structured_json_log(
    demo_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.api.main"):
        resp = demo_client.post("/api/ask", json={"query": "listing 标题最长多少字符？"})
    assert resp.status_code == 200

    records = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "app.api.main" and r.getMessage().startswith("{")
    ]
    ask_records = [r for r in records if r["path"] == "/api/ask"]
    assert len(ask_records) == 1
    entry = ask_records[0]
    assert entry["method"] == "POST"
    assert entry["status"] == 200
    assert entry["latency_ms"] > 0
    assert entry["request_id"] == resp.headers["x-request-id"]
    # Demo Q&A performs retrieval and reports demo token usage.
    assert entry["retrieval_hit"] is True
    assert entry["token_usage"]["calls"] >= 1


def test_stats_endpoint_aggregates(demo_client: TestClient) -> None:
    before = STATS.snapshot()
    assert demo_client.get("/health").status_code == 200
    assert (
        demo_client.post("/api/ask", json={"query": "哪些词属于违禁词？"}).status_code == 200
    )
    resp = demo_client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()

    # The /stats response is assembled before the middleware records the /stats
    # request itself, so only the health + ask calls are visible here.
    assert data["requests_total"] - before["requests_total"] >= 2
    assert data["retrieval_requests"] - before["retrieval_requests"] == 1
    assert data["retrieval_hits"] - before["retrieval_hits"] == 1
    assert 0 <= data["retrieval_hit_rate"] <= 1
    assert data["token_usage"]["calls"] - before["token_usage"]["calls"] >= 1
    assert data["avg_latency_ms"] > 0
    assert data["by_path"]["POST /api/ask"] >= 1
    assert data["demo_mode"] is True
