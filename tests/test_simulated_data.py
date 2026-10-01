"""Tests for simulated operational data generation and querying."""

from __future__ import annotations

from app.data.simulated import SimulatedDataStore, build_simulated_data


def test_build_simulated_data_creates_files(tmp_path) -> None:
    paths = build_simulated_data()
    assert "sales" in paths
    assert "reviews" in paths
    assert "ads" in paths
    for path in paths.values():
        assert path.exists()


def test_data_store_has_expected_tables() -> None:
    store = SimulatedDataStore()
    tables = store.query("SHOW TABLES").to_dict(orient="records")
    table_names = {t["name"] for t in tables}
    assert {"sales", "reviews", "ads"}.issubset(table_names)


def test_review_summary_returns_themes() -> None:
    store = SimulatedDataStore()
    summary = store.summarize_reviews(sku="PP-HR-203", days=90)
    assert len(summary) > 0
    assert all("theme" in row for row in summary)
