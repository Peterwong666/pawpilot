"""Hermetic tests for the metrics API (sales trend + inventory dashboard)."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings

KNOWN_SKUS = {"PP-RT-101", "PP-RT-102", "PP-RT-103", "PP-HR-201", "PP-HR-203", "PP-SB-302"}


_KEY_VARS = ("SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY")


@pytest.fixture
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


def test_sales_trend_demo(demo_client: TestClient):
    resp = demo_client.get("/api/metrics/sales-trend", params={"days": 30})
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 30
    trend = body["trend"]
    assert len(trend) > 0
    for point in trend:
        assert set(point) == {"date", "sku", "units", "revenue"}
        assert point["sku"] in KNOWN_SKUS
        assert point["units"] >= 0
        assert point["revenue"] >= 0.0
    assert {p["sku"] for p in trend} == KNOWN_SKUS


def test_sales_trend_days_clamped(demo_client: TestClient):
    resp = demo_client.get("/api/metrics/sales-trend", params={"days": 1})
    assert resp.status_code == 200
    assert resp.json()["days"] == 7
    resp = demo_client.get("/api/metrics/sales-trend", params={"days": 9999})
    assert resp.status_code == 200
    assert resp.json()["days"] == 180


def test_inventory_demo(demo_client: TestClient):
    resp = demo_client.get("/api/metrics/inventory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 14
    inventory = body["inventory"]
    assert len(inventory) == 6
    for item in inventory:
        assert set(item) == {
            "sku",
            "on_hand",
            "inbound",
            "avg_daily_units",
            "lead_time_days",
            "days_of_cover",
            "status",
        }
        assert item["sku"] in KNOWN_SKUS
        assert item["on_hand"] >= 0
        assert item["avg_daily_units"] >= 0.0
        assert item["status"] in ("ok", "low", "out")
        if item["days_of_cover"] is not None:
            assert item["days_of_cover"] >= 0.0
    # Simulated story: PP-SB-302 is at stockout risk (cover < 12-day lead time).
    sb302 = next(i for i in inventory if i["sku"] == "PP-SB-302")
    assert sb302["status"] in ("low", "out")


def test_inventory_window_param(demo_client: TestClient):
    resp = demo_client.get("/api/metrics/inventory", params={"window_days": 7})
    assert resp.status_code == 200
    assert resp.json()["window_days"] == 7
    resp = demo_client.get("/api/metrics/inventory", params={"window_days": 999})
    assert resp.status_code == 200
    assert resp.json()["window_days"] == 60
