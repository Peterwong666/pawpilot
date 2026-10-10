"""Operational data store backed by PostgreSQL.

Stores real-world data imported from Seller Central / Advertising CSV exports.
When operational records exist for a SKU+date+account, tools prefer them over
simulated data; otherwise they transparently fall back to the simulated dataset.

Tables deliberately mirror the DuckDB simulated schema so existing SQL tools and
scenarios keep working with minimal changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from app.core.config import get_settings
from app.data.simulated import SimulatedDataStore

# Reuse the same process-wide pools as the vector store.
from app.rag.ingestion.store import _get_pool


def _json_safe(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw row dict into JSON-serialisable primitives."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, (date, datetime)):
            out[key] = value.isoformat()
        elif isinstance(value, float) and pd.isna(value):
            out[key] = None
        else:
            out[key] = value
    return out


def _read_df(conn: psycopg.Connection, sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame without pandas DBAPI warnings."""
    with conn.cursor() as cur:
        cur.execute(sql, params or [])
        columns = [desc.name for desc in (cur.description or [])]
        return pd.DataFrame(cur.fetchall(), columns=columns)


@dataclass(frozen=True)
class ImportResult:
    csv_type: str
    rows_imported: int
    warnings: list[str]


class OperationalDataStore:
    """Postgres-backed store for imported Seller Central / Advertising data."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or get_settings().database_url
        self.simulated = SimulatedDataStore()

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        with _get_pool(self.dsn).connection() as conn:
            yield conn

    def init_schema(self) -> None:
        """Create operational tables if they do not exist."""
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS operational_sales (
                        id BIGSERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL DEFAULT 'default',
                        marketplace TEXT NOT NULL DEFAULT 'US',
                        sku TEXT NOT NULL,
                        date DATE NOT NULL,
                        units_sold INTEGER NOT NULL DEFAULT 0,
                        revenue_usd NUMERIC(12,2) NOT NULL DEFAULT 0,
                        sessions INTEGER NOT NULL DEFAULT 0,
                        unit_session_pct NUMERIC(6,3) NOT NULL DEFAULT 0,
                        ad_units INTEGER NOT NULL DEFAULT 0,
                        ad_sales_usd NUMERIC(12,2) NOT NULL DEFAULT 0,
                        data_source TEXT NOT NULL,
                        imported_at TIMESTAMP DEFAULT NOW(),
                        raw_record JSONB,
                        UNIQUE (account_id, marketplace, sku, date, data_source)
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_operational_sales_lookup
                    ON operational_sales(account_id, marketplace, sku, date);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS operational_ads (
                        id BIGSERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL DEFAULT 'default',
                        marketplace TEXT NOT NULL DEFAULT 'US',
                        sku TEXT NOT NULL,
                        date DATE NOT NULL,
                        campaign TEXT,
                        impressions INTEGER NOT NULL DEFAULT 0,
                        clicks INTEGER NOT NULL DEFAULT 0,
                        ad_spend_usd NUMERIC(12,2) NOT NULL DEFAULT 0,
                        ad_sales_usd NUMERIC(12,2) NOT NULL DEFAULT 0,
                        acos_pct NUMERIC(6,2),
                        data_source TEXT NOT NULL,
                        imported_at TIMESTAMP DEFAULT NOW(),
                        raw_record JSONB,
                        UNIQUE (account_id, marketplace, sku, date, campaign, data_source)
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_operational_ads_lookup
                    ON operational_ads(account_id, marketplace, sku, date);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS operational_inventory (
                        id BIGSERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL DEFAULT 'default',
                        marketplace TEXT NOT NULL DEFAULT 'US',
                        sku TEXT NOT NULL,
                        date DATE NOT NULL,
                        on_hand INTEGER NOT NULL DEFAULT 0,
                        inbound INTEGER NOT NULL DEFAULT 0,
                        reserved INTEGER NOT NULL DEFAULT 0,
                        days_of_supply NUMERIC(8,2),
                        restock_lead_time_days INTEGER,
                        data_source TEXT NOT NULL,
                        imported_at TIMESTAMP DEFAULT NOW(),
                        raw_record JSONB,
                        UNIQUE (account_id, marketplace, sku, date, data_source)
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_operational_inventory_lookup
                    ON operational_inventory(account_id, marketplace, sku, date);
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS operational_costs (
                        id BIGSERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL DEFAULT 'default',
                        marketplace TEXT NOT NULL DEFAULT 'US',
                        sku TEXT NOT NULL,
                        price_usd NUMERIC(12,2),
                        cogs_usd NUMERIC(12,2),
                        fba_fee_usd NUMERIC(12,2),
                        referral_fee_pct NUMERIC(5,4) DEFAULT 0.15,
                        restock_lead_time_days INTEGER,
                        data_source TEXT NOT NULL,
                        imported_at TIMESTAMP DEFAULT NOW(),
                        raw_record JSONB,
                        UNIQUE (account_id, marketplace, sku, data_source)
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_operational_costs_lookup
                    ON operational_costs(account_id, marketplace, sku);
                """)
            conn.commit()

    # ------------------------------------------------------------------
    # Write paths
    # ------------------------------------------------------------------
    def import_sales(
        self,
        df: pd.DataFrame,
        account_id: str,
        marketplace: str,
        data_source: str,
    ) -> ImportResult:
        warnings: list[str] = []
        required = {"sku", "date"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns for sales import: {missing}")

        if "units_sold" not in df.columns:
            warnings.append("'units_sold' not found; defaulted to 0")
            df = df.assign(units_sold=0)
        if "revenue_usd" not in df.columns:
            warnings.append("'revenue_usd' not found; defaulted to 0")
            df = df.assign(revenue_usd=0.0)
        if "sessions" not in df.columns:
            warnings.append("'sessions' not found; defaulted to 0")
            df = df.assign(sessions=0)
        if "unit_session_pct" not in df.columns:
            df = df.assign(unit_session_pct=0.0)
        if "ad_units" not in df.columns:
            df = df.assign(ad_units=0)
        if "ad_sales_usd" not in df.columns:
            df = df.assign(ad_sales_usd=0.0)

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["unit_session_pct"] = pd.to_numeric(df["unit_session_pct"], errors="coerce").fillna(0)

        rows = 0
        with self._connection() as conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute("""
                        INSERT INTO operational_sales
                        (account_id, marketplace, sku, date, units_sold, revenue_usd,
                         sessions, unit_session_pct, ad_units, ad_sales_usd,
                         data_source, raw_record)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (account_id, marketplace, sku, date, data_source)
                        DO UPDATE SET
                            units_sold = EXCLUDED.units_sold,
                            revenue_usd = EXCLUDED.revenue_usd,
                            sessions = EXCLUDED.sessions,
                            unit_session_pct = EXCLUDED.unit_session_pct,
                            ad_units = EXCLUDED.ad_units,
                            ad_sales_usd = EXCLUDED.ad_sales_usd,
                            imported_at = NOW(),
                            raw_record = EXCLUDED.raw_record
                    """, (
                        account_id, marketplace, row["sku"], row["date"],
                        int(row["units_sold"]), float(row["revenue_usd"]),
                        int(row["sessions"]), float(row["unit_session_pct"]),
                        int(row["ad_units"]), float(row["ad_sales_usd"]),
                        data_source, Jsonb(_json_safe(row.to_dict())),
                    ))
                    rows += 1
            conn.commit()
        return ImportResult(csv_type="sales", rows_imported=rows, warnings=warnings)

    def import_ads(
        self,
        df: pd.DataFrame,
        account_id: str,
        marketplace: str,
        data_source: str,
    ) -> ImportResult:
        warnings: list[str] = []
        required = {"sku", "date"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns for ads import: {missing}")

        for col in ["impressions", "clicks", "ad_spend_usd", "ad_sales_usd"]:
            if col not in df.columns:
                warnings.append(f"'{col}' not found; defaulted to 0")
                df = df.assign(**{col: 0})
        if "acos_pct" not in df.columns:
            warnings.append("'acos_pct' not found; will compute from spend/sales when possible")
            df = df.assign(acos_pct=None)
        if "campaign" not in df.columns:
            df = df.assign(campaign="default")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["acos_pct"] = pd.to_numeric(df["acos_pct"], errors="coerce")

        rows = 0
        with self._connection() as conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    acos = row["acos_pct"]
                    if pd.isna(acos):
                        sales = float(row["ad_sales_usd"])
                        spend = float(row["ad_spend_usd"])
                        acos = (spend / sales * 100) if sales > 0 else None
                    cur.execute("""
                        INSERT INTO operational_ads
                        (account_id, marketplace, sku, date, campaign, impressions, clicks,
                         ad_spend_usd, ad_sales_usd, acos_pct, data_source, raw_record)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (account_id, marketplace, sku, date, campaign, data_source)
                        DO UPDATE SET
                            impressions = EXCLUDED.impressions,
                            clicks = EXCLUDED.clicks,
                            ad_spend_usd = EXCLUDED.ad_spend_usd,
                            ad_sales_usd = EXCLUDED.ad_sales_usd,
                            acos_pct = EXCLUDED.acos_pct,
                            imported_at = NOW(),
                            raw_record = EXCLUDED.raw_record
                    """, (
                        account_id, marketplace, row["sku"], row["date"], row["campaign"],
                        int(row["impressions"]), int(row["clicks"]),
                        float(row["ad_spend_usd"]), float(row["ad_sales_usd"]),
                        None if acos is None else float(acos),
                        data_source, Jsonb(_json_safe(row.to_dict())),
                    ))
                    rows += 1
            conn.commit()
        return ImportResult(csv_type="ads", rows_imported=rows, warnings=warnings)

    def import_inventory(
        self,
        df: pd.DataFrame,
        account_id: str,
        marketplace: str,
        data_source: str,
    ) -> ImportResult:
        warnings: list[str] = []
        required = {"sku", "date"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns for inventory import: {missing}")

        for col in ["on_hand", "inbound", "reserved"]:
            if col not in df.columns:
                warnings.append(f"'{col}' not found; defaulted to 0")
                df = df.assign(**{col: 0})
        if "days_of_supply" not in df.columns:
            warnings.append("'days_of_supply' not found; will estimate from sales if available")
            df = df.assign(days_of_supply=None)
        if "restock_lead_time_days" not in df.columns:
            warnings.append("'restock_lead_time_days' not found; defaulted to 30")
            df = df.assign(restock_lead_time_days=30)

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date

        rows = 0
        with self._connection() as conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute("""
                        INSERT INTO operational_inventory
                        (account_id, marketplace, sku, date, on_hand, inbound, reserved,
                         days_of_supply, restock_lead_time_days, data_source, raw_record)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (account_id, marketplace, sku, date, data_source)
                        DO UPDATE SET
                            on_hand = EXCLUDED.on_hand,
                            inbound = EXCLUDED.inbound,
                            reserved = EXCLUDED.reserved,
                            days_of_supply = EXCLUDED.days_of_supply,
                            restock_lead_time_days = EXCLUDED.restock_lead_time_days,
                            imported_at = NOW(),
                            raw_record = EXCLUDED.raw_record
                    """, (
                        account_id, marketplace, row["sku"], row["date"],
                        int(row["on_hand"]), int(row["inbound"]), int(row["reserved"]),
                        None if pd.isna(row["days_of_supply"]) else float(row["days_of_supply"]),
                        int(row["restock_lead_time_days"]),
                        data_source, Jsonb(_json_safe(row.to_dict())),
                    ))
                    rows += 1
            conn.commit()
        return ImportResult(csv_type="inventory", rows_imported=rows, warnings=warnings)

    def import_costs(
        self,
        df: pd.DataFrame,
        account_id: str,
        marketplace: str,
        data_source: str,
    ) -> ImportResult:
        warnings: list[str] = []
        required = {"sku"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns for costs import: {missing}")

        for col in ["cogs_usd", "fba_fee_usd"]:
            if col not in df.columns:
                warnings.append(f"'{col}' not found; defaulted to 0")
                df = df.assign(**{col: 0.0})
        if "price_usd" not in df.columns:
            warnings.append("'price_usd' not found; may impact margin analysis")
            df = df.assign(price_usd=None)
        if "referral_fee_pct" not in df.columns:
            df = df.assign(referral_fee_pct=0.15)
        if "restock_lead_time_days" not in df.columns:
            df = df.assign(restock_lead_time_days=30)

        df = df.copy()
        df["referral_fee_pct"] = pd.to_numeric(df["referral_fee_pct"], errors="coerce").fillna(0.15)

        rows = 0
        with self._connection() as conn:
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    cur.execute("""
                        INSERT INTO operational_costs
                        (account_id, marketplace, sku, price_usd, cogs_usd, fba_fee_usd,
                         referral_fee_pct, restock_lead_time_days, data_source, raw_record)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (account_id, marketplace, sku, data_source)
                        DO UPDATE SET
                            price_usd = EXCLUDED.price_usd,
                            cogs_usd = EXCLUDED.cogs_usd,
                            fba_fee_usd = EXCLUDED.fba_fee_usd,
                            referral_fee_pct = EXCLUDED.referral_fee_pct,
                            restock_lead_time_days = EXCLUDED.restock_lead_time_days,
                            imported_at = NOW(),
                            raw_record = EXCLUDED.raw_record
                    """, (
                        account_id, marketplace, row["sku"],
                        None if pd.isna(row["price_usd"]) else float(row["price_usd"]),
                        float(row["cogs_usd"]), float(row["fba_fee_usd"]),
                        float(row["referral_fee_pct"]), int(row["restock_lead_time_days"]),
                        data_source, Jsonb(_json_safe(row.to_dict())),
                    ))
                    rows += 1
            conn.commit()
        return ImportResult(csv_type="costs", rows_imported=rows, warnings=warnings)

    # ------------------------------------------------------------------
    # Read paths: used by tools. Return DataFrames so tools can combine with simulated.
    # ------------------------------------------------------------------
    def get_sales(
        self,
        sku: str | None = None,
        account_id: str = "default",
        marketplace: str = "US",
        days: int | None = None,
    ) -> pd.DataFrame:
        sql = """
            SELECT sku, date, units_sold, revenue_usd, sessions, unit_session_pct,
                   ad_units, ad_sales_usd, data_source
            FROM operational_sales
            WHERE account_id = %s AND marketplace = %s
        """
        params: list[Any] = [account_id, marketplace]
        if sku:
            sql += " AND sku = %s"
            params.append(sku)
        if days:
            sql += " AND date >= CURRENT_DATE - INTERVAL '%s days'"
            params.append(days)
        sql += " ORDER BY sku, date"
        with self._connection() as conn:
            return _read_df(conn, sql, params)

    def get_ads(
        self,
        sku: str | None = None,
        account_id: str = "default",
        marketplace: str = "US",
        days: int | None = None,
    ) -> pd.DataFrame:
        sql = """
            SELECT sku, date, campaign, impressions, clicks, ad_spend_usd,
                   ad_sales_usd, acos_pct, data_source
            FROM operational_ads
            WHERE account_id = %s AND marketplace = %s
        """
        params: list[Any] = [account_id, marketplace]
        if sku:
            sql += " AND sku = %s"
            params.append(sku)
        if days:
            sql += " AND date >= CURRENT_DATE - INTERVAL '%s days'"
            params.append(days)
        sql += " ORDER BY sku, date"
        with self._connection() as conn:
            return _read_df(conn, sql, params)

    def get_inventory(
        self,
        sku: str | None = None,
        account_id: str = "default",
        marketplace: str = "US",
    ) -> pd.DataFrame:
        sql = """
            SELECT sku, date, on_hand, inbound, reserved, days_of_supply,
                   restock_lead_time_days, data_source
            FROM operational_inventory
            WHERE account_id = %s AND marketplace = %s
        """
        params: list[Any] = [account_id, marketplace]
        if sku:
            sql += " AND sku = %s"
            params.append(sku)
        sql += " ORDER BY sku, date"
        with self._connection() as conn:
            return _read_df(conn, sql, params)

    def get_costs(
        self,
        sku: str | None = None,
        account_id: str = "default",
        marketplace: str = "US",
    ) -> pd.DataFrame:
        sql = """
            SELECT sku, price_usd, cogs_usd, fba_fee_usd, referral_fee_pct,
                   restock_lead_time_days, data_source
            FROM operational_costs
            WHERE account_id = %s AND marketplace = %s
        """
        params: list[Any] = [account_id, marketplace]
        if sku:
            sql += " AND sku = %s"
            params.append(sku)
        with self._connection() as conn:
            return _read_df(conn, sql, params)

    def list_accounts(self) -> list[dict[str, str]]:
        sql = """
            SELECT DISTINCT account_id, marketplace
            FROM operational_sales
            UNION
            SELECT DISTINCT account_id, marketplace
            FROM operational_ads
            UNION
            SELECT DISTINCT account_id, marketplace
            FROM operational_inventory
            UNION
            SELECT DISTINCT account_id, marketplace
            FROM operational_costs
            ORDER BY account_id, marketplace
        """
        with self._connection() as conn:
            return _read_df(conn, sql).to_dict(orient="records")

    def has_real_data(self, sku: str | None = None) -> bool:
        """Return True if operational records exist for the SKU (or any SKU if None)."""
        tables = ["operational_sales", "operational_ads", "operational_inventory", "operational_costs"]
        with self._connection() as conn:
            with conn.cursor() as cur:
                for table in tables:
                    sql = f"SELECT 1 FROM {table} WHERE 1=1"
                    params: list[Any] = []
                    if sku:
                        sql += " AND sku = %s"
                        params.append(sku)
                    sql += " LIMIT 1"
                    cur.execute(sql, params)
                    if cur.fetchone():
                        return True
        return False

    # ------------------------------------------------------------------
    # Overview & deletion (data management UI)
    # ------------------------------------------------------------------
    def list_skus(self, account_id: str = "default", marketplace: str = "US") -> list[str]:
        """Return distinct SKUs across all operational tables for an account/marketplace."""
        skus: set[str] = set()
        with self._connection() as conn:
            with conn.cursor() as cur:
                for table in ("operational_sales", "operational_ads", "operational_inventory", "operational_costs"):
                    cur.execute(
                        f"SELECT DISTINCT sku FROM {table} WHERE account_id = %s AND marketplace = %s",
                        (account_id, marketplace),
                    )
                    skus.update(r[0] for r in cur.fetchall())
        return sorted(skus)

    def get_overview(self) -> list[dict[str, Any]]:
        """Return a per-(account_id, marketplace, data_type) summary of imported data."""
        rows: list[dict[str, Any]] = []
        # Tables that have a date column vs. the costs table (per-SKU, no date).
        dated_tables = {
            "sales": "operational_sales",
            "ads": "operational_ads",
            "inventory": "operational_inventory",
        }
        costs_table = "operational_costs"
        with self._connection() as conn:
            with conn.cursor() as cur:
                for data_type, table in dated_tables.items():
                    cur.execute(f"""
                        SELECT account_id, marketplace,
                               COUNT(DISTINCT sku) AS sku_count,
                               COUNT(*) AS row_count,
                               MIN(date) AS min_date,
                               MAX(date) AS max_date,
                               MAX(imported_at) AS last_imported
                        FROM {table}
                        GROUP BY account_id, marketplace
                    """)
                    for r in cur.fetchall():
                        rows.append({
                            "data_type": data_type,
                            "account_id": r[0],
                            "marketplace": r[1],
                            "sku_count": r[2],
                            "row_count": r[3],
                            "min_date": r[4].isoformat() if r[4] else None,
                            "max_date": r[5].isoformat() if r[5] else None,
                            "last_imported": r[6].isoformat() if r[6] else None,
                        })
                # Costs table has no date column.
                cur.execute(f"""
                    SELECT account_id, marketplace,
                           COUNT(DISTINCT sku) AS sku_count,
                           COUNT(*) AS row_count,
                           NULL AS min_date,
                           NULL AS max_date,
                           MAX(imported_at) AS last_imported
                    FROM {costs_table}
                    GROUP BY account_id, marketplace
                """)
                for r in cur.fetchall():
                    rows.append({
                        "data_type": "costs",
                        "account_id": r[0],
                        "marketplace": r[1],
                        "sku_count": r[2],
                        "row_count": r[3],
                        "min_date": None,
                        "max_date": None,
                        "last_imported": r[6].isoformat() if r[6] else None,
                    })
        return rows

    def delete_data(
        self,
        account_id: str,
        marketplace: str,
        csv_type: str | None = None,
    ) -> dict[str, int]:
        """Delete imported operational data for a given account/marketplace (optionally by type).

        Returns a dict of {table: rows_deleted}.
        """
        type_to_table = {
            "sales": "operational_sales",
            "ads": "operational_ads",
            "inventory": "operational_inventory",
            "costs": "operational_costs",
        }
        tables = [type_to_table[csv_type]] if csv_type else list(type_to_table.values())
        deleted: dict[str, int] = {}
        with self._connection() as conn:
            with conn.cursor() as cur:
                for table in tables:
                    cur.execute(
                        f"DELETE FROM {table} WHERE account_id = %s AND marketplace = %s",
                        (account_id, marketplace),
                    )
                    deleted[table] = cur.rowcount
            conn.commit()
        return deleted
