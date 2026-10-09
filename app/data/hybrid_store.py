"""Hybrid operational + simulated data store.

Keeps the fast, deterministic DuckDB simulated tables as the query target while
overlaying real-world records imported from Seller Central / Advertising CSVs.
Real data lives in PostgreSQL; on startup (and after each import) the store
masks the corresponding simulated rows and inserts the imported ones so existing
SQL tools and scenarios continue to work without code changes.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.data.csv_import import CSVType
from app.data.operational_store import OperationalDataStore
from app.data.simulated import SimulatedDataStore


class HybridDataStore:
    """DuckDB-facing store that overlays Postgres operational data on top of simulated data."""

    def __init__(self) -> None:
        self.simulated = SimulatedDataStore()
        self.operational = OperationalDataStore()
        self.operational.init_schema()
        self._sync_from_postgres()

    # ------------------------------------------------------------------
    # DuckDB pass-through
    # ------------------------------------------------------------------
    def query(self, sql: str) -> pd.DataFrame:
        return self.simulated.query(sql)

    def summarize_reviews(self, sku: str | None = None, days: int = 90) -> dict[str, Any]:
        return self.simulated.summarize_reviews(sku=sku, days=days)

    # ------------------------------------------------------------------
    # Operational data sync
    # ------------------------------------------------------------------
    def _sync_from_postgres(self) -> None:
        """Overlay all operational records currently in Postgres onto DuckDB."""
        self._overlay_sales(self.operational.get_sales())
        self._overlay_ads(self.operational.get_ads())
        self._overlay_inventory(self.operational.get_inventory())
        self._overlay_costs(self.operational.get_costs())

    def overlay(self, csv_type: CSVType, df: pd.DataFrame) -> None:
        """Overlay a freshly imported CSV onto DuckDB and persist it to Postgres."""
        if csv_type == "sales":
            self.operational.import_sales(df, account_id="default", marketplace="US", data_source="csv")
            self._overlay_sales(self.operational.get_sales(account_id="default", marketplace="US"))
        elif csv_type == "ads":
            self.operational.import_ads(df, account_id="default", marketplace="US", data_source="csv")
            self._overlay_ads(self.operational.get_ads(account_id="default", marketplace="US"))
        elif csv_type == "inventory":
            self.operational.import_inventory(df, account_id="default", marketplace="US", data_source="csv")
            self._overlay_inventory(self.operational.get_inventory(account_id="default", marketplace="US"))
        elif csv_type == "costs":
            self.operational.import_costs(df, account_id="default", marketplace="US", data_source="csv")
            self._overlay_costs(self.operational.get_costs(account_id="default", marketplace="US"))
        else:
            raise ValueError(f"Unsupported CSV type for overlay: {csv_type}")

    def _overlay_sales(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        # Rename to match DuckDB simulated schema: revenue_usd -> revenue.
        df = df.copy()
        df = df.rename(columns={"revenue_usd": "revenue"})
        # Fill any missing columns with safe defaults so the INSERT always works.
        for col, default in [
            ("units_sold", 0),
            ("revenue", 0.0),
            ("sessions", 0),
            ("unit_session_pct", 0.0),
            ("ad_units", 0),
            ("ad_sales_usd", 0.0),
        ]:
            if col not in df.columns:
                df[col] = default
        # DuckDB simulated sales has: date, sku, units_sold, price, revenue, sessions,
        # unit_session_pct, ad_units, ad_sales_usd.
        # Imported sales may lack price; fill from simulated for matching SKU/date.
        if "price" not in df.columns:
            price_map = self.simulated.query("""
                SELECT DISTINCT sku, price FROM sales
            """).set_index("sku")["price"].to_dict()
            df["price"] = df["sku"].map(price_map)
        # Mask simulated rows only for imported SKU+date pairs: real data wins where it
        # exists, simulated data remains for dates the import does not cover.
        self.simulated.con.register("_imported_sales", df)
        self.simulated.con.execute("""
            DELETE FROM sales WHERE EXISTS (
                SELECT 1 FROM _imported_sales i
                WHERE i.sku = sales.sku AND CAST(i.date AS DATE) = sales.date
            )
        """)
        self.simulated.con.execute("""
            INSERT INTO sales
            SELECT CAST(date AS DATE), sku, units_sold, price, revenue, sessions,
                   unit_session_pct, ad_units, ad_sales_usd
            FROM _imported_sales
        """)
        self.simulated.con.unregister("_imported_sales")

    def _overlay_ads(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        # DuckDB simulated ads has: date, campaign, sku, spend, sales, acos_pct, impressions, clicks.
        df = df.copy()
        df = df.rename(columns={"ad_spend_usd": "spend", "ad_sales_usd": "sales"})
        for col, default in [
            ("spend", 0.0),
            ("sales", 0.0),
            ("acos_pct", 0.0),
            ("impressions", 0),
            ("clicks", 0),
        ]:
            if col not in df.columns:
                df[col] = default
        if "campaign" not in df.columns:
            df["campaign"] = "default"
        self.simulated.con.register("_imported_ads", df)
        self.simulated.con.execute("""
            DELETE FROM ads WHERE EXISTS (
                SELECT 1 FROM _imported_ads i
                WHERE i.sku = ads.sku AND CAST(i.date AS DATE) = ads.date
            )
        """)
        self.simulated.con.execute("""
            INSERT INTO ads
            SELECT CAST(date AS DATE), campaign, sku, spend, sales, acos_pct, impressions, clicks
            FROM _imported_ads
        """)
        self.simulated.con.unregister("_imported_ads")

    def _overlay_inventory(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        # DuckDB simulated inventory has: date, sku, fba_on_hand_units, inbound_units.
        df = df.copy()
        df = df.rename(columns={"on_hand": "fba_on_hand_units", "inbound": "inbound_units"})
        for col, default in [("fba_on_hand_units", 0), ("inbound_units", 0)]:
            if col not in df.columns:
                df[col] = default
        self.simulated.con.register("_imported_inventory", df)
        self.simulated.con.execute("""
            DELETE FROM inventory WHERE EXISTS (
                SELECT 1 FROM _imported_inventory i
                WHERE i.sku = inventory.sku AND CAST(i.date AS DATE) = inventory.date
            )
        """)
        self.simulated.con.execute("""
            INSERT INTO inventory
            SELECT CAST(date AS DATE), sku, fba_on_hand_units, inbound_units
            FROM _imported_inventory
        """)
        self.simulated.con.unregister("_imported_inventory")

    def _overlay_costs(self, df: pd.DataFrame) -> None:
        if df.empty:
            return
        # DuckDB simulated costs has: sku, cogs_usd, fba_fee_usd, referral_fee_pct, restock_lead_time_days.
        df = df.copy()
        for col, default in [
            ("cogs_usd", 0.0),
            ("fba_fee_usd", 0.0),
            ("referral_fee_pct", 0.15),
            ("restock_lead_time_days", 30),
        ]:
            if col not in df.columns:
                df[col] = default
        skus = df["sku"].unique().tolist()
        self.simulated.con.execute(
            "DELETE FROM costs WHERE sku IN (SELECT unnest(?::text[]))", [skus]
        )
        self.simulated.con.register("_imported_costs", df)
        self.simulated.con.execute("""
            INSERT INTO costs
            SELECT sku, cogs_usd, fba_fee_usd, referral_fee_pct, restock_lead_time_days
            FROM _imported_costs
        """)
        self.simulated.con.unregister("_imported_costs")

    def has_real_data(self, sku: str | None = None) -> bool:
        return self.operational.has_real_data(sku=sku)

    def list_accounts(self) -> list[dict[str, str]]:
        return self.operational.list_accounts()
