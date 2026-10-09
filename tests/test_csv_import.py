"""Tests for CSV import: type detection, column mapping, validation, overlay."""

from __future__ import annotations

import pandas as pd

from app.data.csv_import import detect_csv_type, parse_csv, supported_csv_types
from app.data.hybrid_store import HybridDataStore
from app.data.simulated import SimulatedDataStore

SALES_CSV = """SKU,Date,Sessions,Units Ordered,Ordered Product Sales,Unit Session Percentage
PP-RT-102,2024-10-01,120,12,"$179.88",10.00%
PP-RT-102,2024-10-02,110,11,"$164.89",10.00%
PP-SB-302,2024-10-01,95,8,"$135.92",8.42%
"""

ADS_CSV = """Campaign Name,Advertised SKU,Date,Impressions,Clicks,Spend,Sales,ACOS
RopeToy_Search,PP-RT-102,2024-10-01,5000,200,"$52.00","$149.91",34.7%
Harness_Search,PP-HR-203,2024-10-01,6000,250,"$68.00","$175.92",38.6%
"""

INVENTORY_CSV = """Seller SKU,Snapshot Date,AFN Warehouse Quantity,Inbound Quantity,Reserved Quantity,Days of Supply,Lead Time
PP-SB-302,2024-10-01,120,60,10,15.5,20
PP-RT-102,2024-10-01,300,0,20,38.2,25
"""

COSTS_CSV = """SKU,Price,COGS,FBA Fee,Referral Fee,Lead Time
PP-RT-102,14.99,3.20,4.86,0.15,25
PP-SB-302,16.99,3.40,5.09,0.15,20
"""

UNKNOWN_CSV = """col_a,col_b,col_c
1,2,3
"""


def test_detect_sales_type() -> None:
    df = pd.read_csv(pd.io.common.StringIO(SALES_CSV))
    detection = detect_csv_type(df)
    assert detection.csv_type == "sales"
    assert detection.confidence in ("high", "medium")


def test_detect_ads_type() -> None:
    df = pd.read_csv(pd.io.common.StringIO(ADS_CSV))
    detection = detect_csv_type(df)
    assert detection.csv_type == "ads"
    assert detection.confidence in ("high", "medium")


def test_detect_inventory_type() -> None:
    df = pd.read_csv(pd.io.common.StringIO(INVENTORY_CSV))
    detection = detect_csv_type(df)
    assert detection.csv_type == "inventory"


def test_detect_costs_type() -> None:
    df = pd.read_csv(pd.io.common.StringIO(COSTS_CSV))
    detection = detect_csv_type(df)
    assert detection.csv_type == "costs"


def test_parse_sales_csv_normalises_columns() -> None:
    result = parse_csv(SALES_CSV, filename="sales.csv")
    assert result.csv_type == "sales"
    df = result.df
    assert {"sku", "date", "units_sold", "revenue_usd", "sessions"} <= set(df.columns)
    assert df["sku"].iloc[0] == "PP-RT-102"
    assert df["units_sold"].iloc[0] == 12
    # Currency symbols and commas are stripped.
    assert float(df["revenue_usd"].iloc[0]) == 179.88
    # Dates are parsed (ISO format 2024-10-01).
    assert df["date"].iloc[0].isoformat() == "2024-10-01"


def test_parse_ads_csv_strips_currency_and_pct() -> None:
    result = parse_csv(ADS_CSV, filename="ads.csv")
    assert result.csv_type == "ads"
    df = result.df
    assert float(df["ad_spend_usd"].iloc[0]) == 52.0
    assert float(df["acos_pct"].iloc[0]) == 34.7


def test_parse_inventory_csv() -> None:
    result = parse_csv(INVENTORY_CSV, filename="inv.csv")
    assert result.csv_type == "inventory"
    df = result.df
    assert int(df["on_hand"].iloc[0]) == 120
    assert float(df["days_of_supply"].iloc[0]) == 15.5


def test_parse_costs_csv() -> None:
    result = parse_csv(COSTS_CSV, filename="costs.csv")
    assert result.csv_type == "costs"
    df = result.df
    assert float(df["cogs_usd"].iloc[0]) == 3.2
    assert float(df["fba_fee_usd"].iloc[0]) == 4.86


def test_unknown_csv_raises() -> None:
    try:
        parse_csv(UNKNOWN_CSV, filename="unknown.csv")
    except ValueError as exc:
        assert "Could not detect CSV type" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown CSV")


def test_supported_types_metadata() -> None:
    types = supported_csv_types()
    assert {t["type"] for t in types} == {"sales", "ads", "inventory", "costs"}


def test_hybrid_store_overlay_sales_replaces_simulated() -> None:
    """Imported sales rows must override simulated rows for the same SKU+date."""
    store = HybridDataStore.__new__(HybridDataStore)
    store.simulated = SimulatedDataStore()
    calls: list[tuple[str, pd.DataFrame]] = []

    class StubOperational:
        def import_sales(self, df, account_id, marketplace, data_source):
            calls.append(("import_sales", df))
            return None

        def import_ads(self, df, account_id, marketplace, data_source):
            return None

        def import_inventory(self, df, account_id, marketplace, data_source):
            return None

        def import_costs(self, df, account_id, marketplace, data_source):
            return None

        def get_sales(self, **kwargs):
            return calls[0][1].rename(columns={"revenue_usd": "revenue"}) if calls else pd.DataFrame()

        def get_ads(self, **kwargs):
            return pd.DataFrame()

        def get_inventory(self, **kwargs):
            return pd.DataFrame()

        def get_costs(self, **kwargs):
            return pd.DataFrame()

    store.operational = StubOperational()

    parsed = parse_csv(SALES_CSV, filename="sales.csv")
    df = parsed.df.copy()
    # Shift imported dates onto existing simulated dates so masking is observable.
    sim_dates = store.query(
        "SELECT DISTINCT date FROM sales WHERE sku = 'PP-RT-102' ORDER BY date"
    )["date"].tolist()
    original = store.query("SELECT * FROM sales WHERE sku = 'PP-RT-102'")
    df["date"] = sim_dates[: len(df)]
    store.overlay("sales", df)

    assert calls, "import_sales must be called on the operational store"
    out = store.query("SELECT * FROM sales WHERE sku = 'PP-RT-102' ORDER BY date")
    # Real data replaces simulated rows only on imported dates; other dates fall back.
    assert len(out) == len(original)
    replaced = out[out["date"].isin(sim_dates[: len(df)])]
    assert len(replaced) == len(df)
    assert float(replaced["revenue"].iloc[0]) == 179.88
