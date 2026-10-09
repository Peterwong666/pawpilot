"""CSV import pipeline for Seller Central and Advertising reports.

Responsible for:
1. Detecting the report type from column headers.
2. Normalising column names to a canonical schema.
3. Validating required and numeric fields.
4. Returning a clean DataFrame ready for OperationalDataStore.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import Any

import pandas as pd

CSVType = str


@dataclass(frozen=True)
class CSVDetection:
    csv_type: CSVType
    confidence: str  # 'high' | 'medium' | 'low'
    matched_columns: list[str]
    missing_columns: list[str]


@dataclass(frozen=True)
class CSVParseResult:
    csv_type: CSVType
    df: pd.DataFrame
    detection: CSVDetection
    warnings: list[str]


# Canonical internal column names.
SALES_COLUMNS = {
    "sku": ["sku", "child asin", "asin", "product sku", "seller sku", "item id"],
    "date": ["date", " reporting date", "snapshot date"],
    "units_sold": ["units ordered", "units", "total order items", "quantity"],
    "revenue_usd": ["ordered product sales", "product sales", "revenue", "sales"],
    "sessions": ["sessions", "session", "unique visitors"],
    "unit_session_pct": ["unit session percentage", "conversion rate", "order session %", "units/session"],
    "ad_units": ["ad units", "sponsored units"],
    "ad_sales_usd": ["ad sales", "sponsored sales"],
}

ADS_COLUMNS = {
    "sku": ["sku", "asin", "advertised sku", "advertised asin"],
    "date": ["date", "reporting date", "start date"],
    "campaign": ["campaign name", "campaign", "ad group name"],
    "impressions": ["impressions", "impr."],
    "clicks": ["clicks", "click"],
    "ad_spend_usd": ["spend", "cost", "ad spend", "total spend"],
    "ad_sales_usd": ["sales", "ad sales", "total sales", "attributed sales"],
    "acos_pct": ["acos", "total acos", "advertising cost of sales"],
}

INVENTORY_COLUMNS = {
    "sku": ["sku", "seller sku", "fulfillment channel sku"],
    "date": ["date", "snapshot date"],
    "on_hand": ["afn warehouse quantity", "fulfillable quantity", "available", "on hand", "quantity available"],
    "inbound": ["inbound quantity", "inbound", "incoming"],
    "reserved": ["reserved quantity", "reserved", "reserved fc transfer"],
    "days_of_supply": ["days of supply", "estimated days of supply"],
    "restock_lead_time_days": ["lead time", "restock lead time", "supplier lead time"],
}

COSTS_COLUMNS = {
    "sku": ["sku", "asin", "product sku"],
    "price_usd": ["price", "selling price", "retail price"],
    "cogs_usd": ["cogs", "landed cost", "unit cost"],
    "fba_fee_usd": ["fba fee", "fulfillment fee", "fba per unit"],
    "referral_fee_pct": ["referral fee", "referral fee pct", "commission"],
    "restock_lead_time_days": ["lead time", "restock lead time"],
}

_SCHEMAS: dict[CSVType, dict[str, list[str]]] = {
    "sales": SALES_COLUMNS,
    "ads": ADS_COLUMNS,
    "inventory": INVENTORY_COLUMNS,
    "costs": COSTS_COLUMNS,
}

_REQUIRED_BY_TYPE: dict[CSVType, set[str]] = {
    "sales": {"sku", "date"},
    "ads": {"sku", "date"},
    "inventory": {"sku", "date"},
    "costs": {"sku"},
}

_NUMERIC_COLUMNS: dict[str, list[str]] = {
    "sales": ["units_sold", "revenue_usd", "sessions", "unit_session_pct", "ad_units", "ad_sales_usd"],
    "ads": ["impressions", "clicks", "ad_spend_usd", "ad_sales_usd", "acos_pct"],
    "inventory": ["on_hand", "inbound", "reserved", "days_of_supply", "restock_lead_time_days"],
    "costs": ["price_usd", "cogs_usd", "fba_fee_usd", "referral_fee_pct", "restock_lead_time_days"],
}


def _normalise_header(header: str) -> str:
    """Lower-case, strip, collapse spaces, remove currency units and trailing punctuation."""
    h = header.lower().strip()
    h = h.replace("(", " ").replace(")", " ")
    h = h.replace("$", "")
    h = h.replace("  ", " ")
    return h.strip()


def _build_column_mapping(
    headers: list[str], schema: dict[str, list[str]]
) -> tuple[dict[str, str], list[str], list[str]]:
    """Map raw headers to canonical names.

    Returns (canonical_to_raw, matched_canonical, missing_canonical).
    """
    normalised = {_normalise_header(h): h for h in headers}
    mapping: dict[str, str] = {}
    matched: list[str] = []
    missing: list[str] = []
    for canonical, aliases in schema.items():
        found = None
        for alias in aliases:
            if alias in normalised:
                found = normalised[alias]
                break
        if found:
            mapping[canonical] = found
            matched.append(canonical)
        else:
            missing.append(canonical)
    return mapping, matched, missing


def detect_csv_type(
    df: pd.DataFrame, threshold_high: float = 0.6, threshold_medium: float = 0.35
) -> CSVDetection:
    """Detect the CSV report type from its headers."""
    headers = [str(c) for c in df.columns]
    best_type: CSVType | None = None
    best_ratio = 0.0
    best_matched: list[str] = []
    best_missing: list[str] = []

    for csv_type, schema in _SCHEMAS.items():
        mapping, matched, missing = _build_column_mapping(headers, schema)
        total = len(schema)
        ratio = len(matched) / total if total else 0
        # Required columns must be present to even qualify.
        required_present = len(_REQUIRED_BY_TYPE[csv_type] & set(matched))
        if required_present == len(_REQUIRED_BY_TYPE[csv_type]) and ratio > best_ratio:
            best_type = csv_type
            best_ratio = ratio
            best_matched = matched
            best_missing = missing

    if best_type is None:
        return CSVDetection(csv_type="unknown", confidence="low", matched_columns=[], missing_columns=[])

    if best_ratio >= threshold_high:
        confidence = "high"
    elif best_ratio >= threshold_medium:
        confidence = "medium"
    else:
        confidence = "low"

    return CSVDetection(
        csv_type=best_type,
        confidence=confidence,
        matched_columns=best_matched,
        missing_columns=best_missing,
    )


def _coerce_numeric(df: pd.DataFrame, columns: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Strip commas/currency symbols and coerce numeric columns. Returns (df, warnings)."""
    warnings: list[str] = []
    for col in columns:
        if col not in df.columns:
            continue
        # Remove common formatting artifacts.
        cleaned = (
            df[col]
            .astype(str)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.strip()
        )
        # Replace sentinel values with NaN.
        cleaned = cleaned.replace(["-", "", "N/A", "n/a"], pd.NA)
        numeric = pd.to_numeric(cleaned, errors="coerce")
        bad = numeric.isna() & cleaned.notna()
        if bad.any():
            warnings.append(f"Could not parse {bad.sum()} value(s) in '{col}'; treated as missing")
        df[col] = numeric
    return df, warnings


def parse_csv(
    content: str | bytes,
    filename: str = "data.csv",
    encoding: str = "utf-8",
) -> CSVParseResult:
    """Parse a CSV string/bytes into a normalised DataFrame with type detection."""
    if isinstance(content, bytes):
        content = content.decode(encoding)

    # Try common separators; default to comma.
    for sep in [",", "\t", ";"]:
        try:
            df = pd.read_csv(StringIO(content), sep=sep, dtype=str, keep_default_na=False)
            if len(df.columns) > 1:
                break
        except Exception:
            continue
    else:
        raise ValueError("Could not parse CSV: unable to determine separator.")

    if df.empty:
        raise ValueError("CSV file is empty.")

    detection = detect_csv_type(df)
    if detection.csv_type == "unknown":
        raise ValueError(
            f"Could not detect CSV type from headers: {list(df.columns)}. "
            "Expected Seller Central Business Report, Advertising Campaign Report, "
            "FBA Inventory Report, or SKU cost sheet."
        )
    if detection.confidence == "low":
        raise ValueError(
            f"CSV type detection is uncertain ({detection.csv_type}). "
            f"Matched columns: {detection.matched_columns}. "
            f"Missing columns: {detection.missing_columns}."
        )

    schema = _SCHEMAS[detection.csv_type]
    mapping, _, _ = _build_column_mapping([str(c) for c in df.columns], schema)

    # Rename raw columns to canonical names.
    df = df.rename(columns={raw: canonical for canonical, raw in mapping.items()})

    # Keep only canonical columns.
    canonical_cols = list(schema.keys())
    df = df[[c for c in canonical_cols if c in df.columns]]

    warnings: list[str] = []

    # Normalise date column.
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        bad_dates = df["date"].isna().sum()
        if bad_dates:
            warnings.append(f"Could not parse {bad_dates} date value(s); rows dropped")
            df = df.dropna(subset=["date"])

    # Normalise SKU.
    df["sku"] = df["sku"].astype(str).str.strip().str.upper()
    df = df[df["sku"].notna() & (df["sku"] != "")]

    # Coerce numeric columns.
    df, num_warnings = _coerce_numeric(df, _NUMERIC_COLUMNS.get(detection.csv_type, []))
    warnings.extend(num_warnings)

    # Drop rows missing required fields.
    required = _REQUIRED_BY_TYPE[detection.csv_type]
    before = len(df)
    df = df.dropna(subset=[c for c in required if c in df.columns])
    dropped = before - len(df)
    if dropped:
        warnings.append(f"Dropped {dropped} row(s) missing required fields")

    return CSVParseResult(
        csv_type=detection.csv_type,
        df=df.reset_index(drop=True),
        detection=detection,
        warnings=warnings,
    )


def supported_csv_types() -> list[dict[str, Any]]:
    """Return human-readable metadata about supported CSV types."""
    return [
        {
            "type": "sales",
            "name": "Seller Central Business Report",
            "required_columns": sorted(_REQUIRED_BY_TYPE["sales"]),
            "recognisable_headers": ["SKU", "Date", "Units Ordered", "Ordered Product Sales", "Sessions"],
        },
        {
            "type": "ads",
            "name": "Advertising Campaign Report",
            "required_columns": sorted(_REQUIRED_BY_TYPE["ads"]),
            "recognisable_headers": ["SKU", "Date", "Impressions", "Clicks", "Spend", "Sales", "ACOS"],
        },
        {
            "type": "inventory",
            "name": "FBA Inventory Report",
            "required_columns": sorted(_REQUIRED_BY_TYPE["inventory"]),
            "recognisable_headers": ["SKU", "Date", "AFN Warehouse Quantity", "Inbound", "Reserved"],
        },
        {
            "type": "costs",
            "name": "SKU Cost & Margin Sheet",
            "required_columns": sorted(_REQUIRED_BY_TYPE["costs"]),
            "recognisable_headers": ["SKU", "COGS", "FBA Fee", "Referral Fee", "Lead Time"],
        },
    ]
