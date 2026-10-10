"""Tests for simulated operational data generation and querying.

Includes ground-truth assertions for the embedded anomaly story so diagnosis and
digest scenarios can be validated deterministically.
"""

from __future__ import annotations

from app.data.simulated import (
    ACOS_TARGET_PCT,
    ALLOWED_TABLES,
    ANOMALY_ACOS_SKU,
    ANOMALY_INVENTORY_SKU,
    ANOMALY_REVIEW_WINDOW_DAYS,
    ANOMALY_SALES_SKU,
    ANOMALY_SALES_WINDOW_DAYS,
    SimulatedDataStore,
    build_simulated_data,
)


def test_build_simulated_data_creates_files(tmp_path) -> None:
    paths = build_simulated_data()
    assert ALLOWED_TABLES == set(paths)
    for path in paths.values():
        assert path.exists()


def test_data_store_has_expected_tables() -> None:
    store = SimulatedDataStore()
    tables = store.query("SHOW TABLES").to_dict(orient="records")
    table_names = {t["name"] for t in tables}
    assert ALLOWED_TABLES == table_names


def test_review_summary_returns_themes() -> None:
    store = SimulatedDataStore()
    summary = store.summarize_reviews(sku="PP-HR-203", days=90)
    assert len(summary) > 0
    assert all("theme" in row for row in summary)


def test_anomaly_units_drop() -> None:
    """PP-RT-102 units in the anomaly window must be <= 70% of the prior window."""
    store = SimulatedDataStore()
    row = store.query(f"""
        SELECT
          SUM(CASE WHEN date >= CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS} days'
               THEN units_sold ELSE 0 END) AS cur_units,
          SUM(CASE WHEN date < CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS} days'
                    AND date >= CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS * 2} days'
               THEN units_sold ELSE 0 END) AS prev_units
        FROM sales WHERE sku = '{ANOMALY_SALES_SKU}'
    """).to_dict(orient="records")[0]
    assert row["prev_units"] > 0
    assert row["cur_units"] / row["prev_units"] <= 0.70


def test_anomaly_cvr_drop() -> None:
    """PP-RT-102 conversion rate must drop by at least 28% (relative)."""
    store = SimulatedDataStore()
    row = store.query(f"""
        SELECT
          AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS} days'
               THEN unit_session_pct END) AS cur_cvr,
          AVG(CASE WHEN date < CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS} days'
                    AND date >= CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS * 2} days'
               THEN unit_session_pct END) AS prev_cvr
        FROM sales WHERE sku = '{ANOMALY_SALES_SKU}'
    """).to_dict(orient="records")[0]
    assert row["prev_cvr"] > 0
    assert row["cur_cvr"] / row["prev_cvr"] <= 0.72


def test_anomaly_rating_drop() -> None:
    """PP-RT-102 average rating must drop by at least 0.4 in the review anomaly window."""
    store = SimulatedDataStore()
    row = store.query(f"""
        SELECT
          AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '{ANOMALY_REVIEW_WINDOW_DAYS} days'
               THEN rating END) AS cur_rating,
          AVG(CASE WHEN date < CURRENT_DATE - INTERVAL '{ANOMALY_REVIEW_WINDOW_DAYS} days'
                    AND date >= CURRENT_DATE - INTERVAL '{ANOMALY_REVIEW_WINDOW_DAYS * 2} days'
               THEN rating END) AS prev_rating
        FROM reviews WHERE sku = '{ANOMALY_SALES_SKU}'
    """).to_dict(orient="records")[0]
    assert row["prev_rating"] - row["cur_rating"] >= 0.4


def test_anomaly_ad_spend_cut() -> None:
    """RopeToy_Search spend must be cut by at least 60% in the anomaly window."""
    store = SimulatedDataStore()
    row = store.query(f"""
        SELECT
          SUM(CASE WHEN date >= CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS} days'
               THEN spend ELSE 0 END) AS cur_spend,
          SUM(CASE WHEN date < CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS} days'
                    AND date >= CURRENT_DATE - INTERVAL '{ANOMALY_SALES_WINDOW_DAYS * 2} days'
               THEN spend ELSE 0 END) AS prev_spend
        FROM ads WHERE sku = '{ANOMALY_SALES_SKU}'
    """).to_dict(orient="records")[0]
    assert row["prev_spend"] > 0
    assert row["cur_spend"] / row["prev_spend"] <= 0.40  # >=60% cut


def test_anomaly_inventory_below_lead_time() -> None:
    """PP-SB-302 inventory cover must fall below its 20-day replenishment lead time."""
    store = SimulatedDataStore()
    row = store.query(f"""
        SELECT
          (SELECT fba_on_hand_units FROM inventory
            WHERE sku = '{ANOMALY_INVENTORY_SKU}' AND date = (SELECT MAX(date) FROM inventory)) AS on_hand,
          (SELECT AVG(units_sold) FROM sales
            WHERE sku = '{ANOMALY_INVENTORY_SKU}' AND date >= CURRENT_DATE - INTERVAL '7 days') AS avg_daily
    """).to_dict(orient="records")[0]
    cover_days = row["on_hand"] / row["avg_daily"]
    lead_time = store.query(
        f"SELECT restock_lead_time_days AS d FROM costs WHERE sku = '{ANOMALY_INVENTORY_SKU}'"
    ).to_dict(orient="records")[0]["d"]
    assert cover_days < lead_time


def test_anomaly_acos_above_target() -> None:
    """PP-HR-203 ACOS in the last 14 days must exceed target + 5pp."""
    store = SimulatedDataStore()
    row = store.query(f"""
        SELECT AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '14 days' THEN acos_pct END) AS cur_acos
        FROM ads WHERE sku = '{ANOMALY_ACOS_SKU}'
    """).to_dict(orient="records")[0]
    assert row["cur_acos"] > ACOS_TARGET_PCT + 5


def test_competitor_reviews_have_product_lines() -> None:
    store = SimulatedDataStore()
    rows = store.query(
        "SELECT product_type, COUNT(*) AS n FROM competitor_reviews GROUP BY product_type"
    ).to_dict(orient="records")
    by_type = {r["product_type"]: r["n"] for r in rows}
    assert {"rope toy", "harness", "feeder bowl"} == set(by_type)
    assert all(n >= 30 for n in by_type.values())
