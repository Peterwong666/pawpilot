"""Tests for the deterministic business-analytics tools (no LLM calls)."""

from __future__ import annotations

import pytest

from app.agent.tools import ToolRegistry, validate_readonly_sql
from app.data.simulated import (
    ANOMALY_INVENTORY_SKU,
    ANOMALY_SALES_SKU,
    SimulatedDataStore,
)
from app.scenarios.compliance_engine import ComplianceRuleEngine


@pytest.fixture()
def registry() -> ToolRegistry:
    """Registry with only the deterministic parts wired (no retriever / DB / LLM)."""
    reg = ToolRegistry.__new__(ToolRegistry)
    reg.data_store = SimulatedDataStore()
    reg.rule_engine = ComplianceRuleEngine()
    return reg


async def test_diagnosis_attributes_the_anomaly_story(registry: ToolRegistry) -> None:
    result = await registry.diagnose_sales_anomaly(ANOMALY_SALES_SKU, days=14)
    assert result["status"] == "anomaly_detected"
    causes = {c["cause"] for c in result["suspected_causes"]}
    # Ground truth: rating decline + ad pause compound into the unit drop.
    assert {"ad_budget_cut", "rating_decline"}.issubset(causes)
    assert result["metrics"]["change_pct"]["units"] <= -20
    # Every cause carries evidence and playbook steps exist.
    for cause in result["suspected_causes"]:
        assert cause["evidence"]
        assert cause["confidence"] in ("high", "medium")
    assert result["recommended_next_steps"]


async def test_diagnosis_normal_sku_reports_normal(registry: ToolRegistry) -> None:
    result = await registry.diagnose_sales_anomaly("PP-HR-201", days=14)
    assert result["status"] == "normal"
    assert result["suspected_causes"] == []


async def test_diagnosis_rejects_bad_sku(registry: ToolRegistry) -> None:
    with pytest.raises(ValueError, match="Invalid SKU"):
        await registry.diagnose_sales_anomaly("PP'; DROP TABLE sales;--")


async def test_profit_math(registry: ToolRegistry) -> None:
    # PP-RT-102: price 14.99, referral 15%, FBA 4.86, COGS 3.20.
    result = await registry.analyze_profit("PP-RT-102")
    assert result["price"] == 14.99
    assert result["fees"]["referral_fee"] == pytest.approx(2.25, abs=0.01)
    assert result["margin_per_unit"] == pytest.approx(4.68, abs=0.02)
    assert result["margin_pct"] == pytest.approx(31.2, abs=0.5)
    # Break-even: (fba + cogs) / (1 - referral) = 8.06 / 0.85 = 9.48.
    assert result["break_even_price"] == pytest.approx(9.48, abs=0.01)
    assert result["est_monthly_profit"] > 0


async def test_profit_what_if_price(registry: ToolRegistry) -> None:
    base = await registry.analyze_profit("PP-RT-102")
    what_if = await registry.analyze_profit("PP-RT-102", price=12.99)
    assert what_if["what_if_price"] is True
    assert what_if["margin_per_unit"] < base["margin_per_unit"]
    assert what_if["break_even_price"] == base["break_even_price"]


async def test_profit_rejects_unknown_sku(registry: ToolRegistry) -> None:
    with pytest.raises(ValueError, match="Unknown SKU"):
        await registry.analyze_profit("PP-XX-999")


async def test_inventory_flags_stockout_story(registry: ToolRegistry) -> None:
    result = await registry.check_inventory_health()
    by_sku = {r["sku"]: r for r in result["skus"]}
    critical = by_sku[ANOMALY_INVENTORY_SKU]
    assert critical["status"] == "critical"
    assert critical["days_of_cover"] < critical["restock_lead_time_days"]
    assert critical["must_order_within_days"] < 0
    # All other SKUs must be healthy (no false stockout alerts).
    for sku, row in by_sku.items():
        if sku != ANOMALY_INVENTORY_SKU:
            assert row["status"] == "healthy", f"{sku} unexpectedly {row['status']}"


async def test_inventory_single_sku_filter(registry: ToolRegistry) -> None:
    result = await registry.check_inventory_health("PP-RT-102")
    assert [r["sku"] for r in result["skus"]] == ["PP-RT-102"]


async def test_voc_mining_aggregates_themes(registry: ToolRegistry) -> None:
    result = await registry.mine_competitor_reviews("rope toy", top_n=10)
    assert result["product_type"] == "rope toy"
    assert result["total_reviews"] >= 30
    counts = [t["count"] for t in result["themes"]]
    assert counts == sorted(counts, reverse=True)  # sorted by frequency
    # Unmet needs (negative themes) must dominate the non-positive rows.
    negative = [t for t in result["themes"] if t["theme"] != "positive"]
    assert len(negative) >= 3
    for theme in negative:
        assert theme["negative_share_pct"] == 100.0
        assert len(theme["sample_quotes"]) >= 1


async def test_voc_mining_rejects_unknown_type(registry: ToolRegistry) -> None:
    with pytest.raises(ValueError, match="Unknown product_type"):
        await registry.mine_competitor_reviews("laser pointer")


async def test_daily_digest_alerts_match_story(registry: ToolRegistry) -> None:
    digest = await registry.generate_daily_digest()
    alerts = {(a["type"], a["sku"]) for a in digest["alerts"]}
    # The three designed stories must surface.
    assert ("sales_drop", ANOMALY_SALES_SKU) in alerts
    assert ("rating_decline", ANOMALY_SALES_SKU) in alerts
    assert ("stockout_risk", ANOMALY_INVENTORY_SKU) in alerts
    assert ("acos_above_target", "PP-HR-203") in alerts
    # Rows carry the full portfolio picture.
    assert len(digest["sku_rows"]) == 6
    for row in digest["sku_rows"]:
        assert {"sku", "units_wow_pct", "revenue_7d", "margin_pct", "rating_7d",
                "inventory_status"}.issubset(row)


def test_sql_guard_accepts_valid_selects() -> None:
    assert validate_readonly_sql("SELECT * FROM sales LIMIT 5") is None
    assert validate_readonly_sql("with x as (select 1 as a from costs) select a from x") is None


def test_sql_guard_rejects_writes_and_unscoped_queries() -> None:
    assert "read-only" in validate_readonly_sql("UPDATE sales SET units_sold = 0")
    assert "read-only" in validate_readonly_sql("DELETE FROM reviews")
    assert "read-only" in validate_readonly_sql("DROP TABLE sales")
    assert "read-only" in validate_readonly_sql("INSERT INTO costs VALUES ('x', 1, 1, 0.15, 10)")
    assert "Multiple statements" in validate_readonly_sql("SELECT 1 FROM sales; SELECT 2 FROM ads")
    assert "allowed table" in validate_readonly_sql("SELECT * FROM sqlite_master")
    assert "allowed table" in validate_readonly_sql("SELECT 1")
    assert "Empty" in validate_readonly_sql("")
