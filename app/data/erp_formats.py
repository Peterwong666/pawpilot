"""ERP / marketplace order-export format registry with auto-detection.

Seller Central / Advertising CSVs are handled by :mod:`app.data.csv_import`.
This module covers a second family of feeds: order-level exports from Chinese
e-commerce ERPs and marketplaces (Taobao/Tmall order export, JD order export),
which differ in three ways from the Amazon reports:

1. Headers are Chinese and platform-specific → per-format column mapping.
2. Files are usually GBK/GB18030 encoded (Excel-era exports) → encoding probing.
3. Rows are individual orders, not per-day aggregates → aggregation to the
   canonical ``(sku, date)`` sales schema on parse.

Adding a new format means appending one :class:`ERPFormat` entry to
:data:`ERP_FORMATS` — detection, mapping and parsing pick it up automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import TypedDict

import pandas as pd

from app.data.csv_import import CSVDetection, CSVParseResult

# Encodings tried in order. utf-8-sig also covers plain UTF-8; GBK is the
# de-facto standard for Chinese ERP Excel exports (GB18030 is a superset
# fallback for rarer characters).
ENCODING_CANDIDATES: tuple[str, ...] = ("utf-8-sig", "gb18030")


@dataclass(frozen=True)
class ERPFormat:
    """One detectable ERP export format.

    Attributes:
        format_id: Stable identifier, e.g. ``taobao_order``.
        name: Human-readable label shown in logs / UI.
        csv_type: Canonical report type the file maps to (currently ``sales``).
        signature_headers: Headers that must ALL be present for detection.
            Chosen to be unique to the platform so formats never overlap.
        column_mapping: canonical column → candidate raw headers (first match wins).
        status_column: Raw header holding the order status; rows whose status
            indicates cancellation/refund are dropped before aggregation.
        cancelled_statuses: Status values treated as non-revenue.
    """

    format_id: str
    name: str
    csv_type: str
    signature_headers: tuple[str, ...]
    column_mapping: dict[str, tuple[str, ...]]
    status_column: str | None = None
    cancelled_statuses: tuple[str, ...] = ()


TAOBAO_ORDER = ERPFormat(
    format_id="taobao_order",
    name="淘宝/天猫订单导出",
    csv_type="sales",
    signature_headers=("订单编号", "宝贝标题", "商家编码"),
    column_mapping={
        "sku": ("商家编码", "商品编码", "商家货号"),
        "date": ("订单创建时间", "创建时间", "付款时间"),
        "units_sold": ("购买数量", "宝贝数量", "数量"),
        "revenue_usd": ("买家实际支付金额", "实付金额", "成交金额"),
    },
    status_column="订单状态",
    cancelled_statuses=("交易关闭", "已关闭", "退款成功"),
)

JINGDONG_ORDER = ERPFormat(
    format_id="jingdong_order",
    name="京东订单导出",
    csv_type="sales",
    signature_headers=("订单号", "商品编号", "下单时间"),
    column_mapping={
        "sku": ("商品编号", "商家SKU", "SKU"),
        "date": ("下单时间", "订单时间", "付款时间"),
        "units_sold": ("商品数量", "订购数量", "数量"),
        "revenue_usd": ("实付金额", "订单金额", "成交金额"),
    },
    status_column="订单状态",
    cancelled_statuses=("已取消", "已关闭", "退款成功"),
)

ERP_FORMATS: tuple[ERPFormat, ...] = (TAOBAO_ORDER, JINGDONG_ORDER)


def decode_csv_bytes(content: bytes) -> tuple[str, str]:
    """Decode CSV bytes by probing :data:`ENCODING_CANDIDATES`.

    Returns ``(text, encoding_used)``. Raises ``ValueError`` when no candidate
    decodes cleanly.
    """
    for encoding in ENCODING_CANDIDATES:
        try:
            return content.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(
        f"Could not decode CSV with any known encoding: {ENCODING_CANDIDATES}"
    )


def detect_erp_format(headers: list[str]) -> ERPFormat | None:
    """Return the first registry format whose signature headers are all present.

    Header comparison strips whitespace; signature headers are platform-unique
    so first-match-wins is unambiguous.
    """
    normalised = {h.strip() for h in headers}
    for fmt in ERP_FORMATS:
        if all(sig in normalised for sig in fmt.signature_headers):
            return fmt
    return None


def _resolve_columns(fmt: ERPFormat, headers: list[str]) -> tuple[dict[str, str], list[str]]:
    """Map canonical columns to raw headers. Returns (canonical_to_raw, missing)."""
    raw_by_stripped = {h.strip(): h for h in headers}
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for canonical, candidates in fmt.column_mapping.items():
        found = None
        for cand in candidates:
            if cand.strip() in raw_by_stripped:
                found = raw_by_stripped[cand.strip()]
                break
        if found is not None:
            mapping[canonical] = found
        else:
            missing.append(canonical)
    return mapping, missing


def parse_erp_csv(content: str | bytes, filename: str = "erp.csv") -> CSVParseResult:
    """Parse an ERP order export into the canonical sales schema.

    Order-level rows are aggregated to ``(sku, date)`` with summed units and
    revenue so the result can go straight into the same overlay path as
    Amazon Business Report rows.
    """
    encoding = "utf-8-sig"
    if isinstance(content, bytes):
        content, encoding = decode_csv_bytes(content)

    # Chinese ERP exports are comma- or tab-separated.
    df: pd.DataFrame | None = None
    for sep in [",", "\t", ";"]:
        try:
            candidate = pd.read_csv(StringIO(content), sep=sep, dtype=str, keep_default_na=False)
            if len(candidate.columns) > 1:
                df = candidate
                break
        except Exception:  # noqa: BLE001 — try the next separator
            continue
    if df is None:
        raise ValueError("Could not parse ERP CSV: unable to determine separator.")
    if df.empty:
        raise ValueError("ERP CSV file is empty.")

    headers = [str(c) for c in df.columns]
    fmt = detect_erp_format(headers)
    if fmt is None:
        raise ValueError(
            f"Could not detect ERP format from headers: {headers}. "
            f"Known formats: {[(f.format_id, f.signature_headers) for f in ERP_FORMATS]}"
        )

    mapping, missing = _resolve_columns(fmt, headers)
    if missing:
        raise ValueError(
            f"Detected {fmt.name} ({fmt.format_id}) but required columns are missing: "
            f"{missing}. Expected one of {fmt.column_mapping}"
        )

    warnings: list[str] = [f"Decoded with encoding '{encoding}'"]

    # Drop cancelled / refunded orders when a status column is present.
    if fmt.status_column and fmt.status_column in df.columns:
        before = len(df)
        df = df[~df[fmt.status_column].str.strip().isin(fmt.cancelled_statuses)]
        dropped = before - len(df)
        if dropped:
            warnings.append(f"Dropped {dropped} cancelled/refunded order(s)")

    df = df.rename(columns={raw: canonical for canonical, raw in mapping.items()})

    # Normalise values.
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    bad_dates = df["date"].isna().sum()
    if bad_dates:
        warnings.append(f"Could not parse {bad_dates} date value(s); rows dropped")
        df = df.dropna(subset=["date"])
    df["sku"] = df["sku"].astype(str).str.strip().str.upper()
    df = df[df["sku"] != ""]
    for col in ("units_sold", "revenue_usd"):
        cleaned = (
            df[col]
            .astype(str)
            .str.replace("¥", "", regex=False)
            .str.replace("￥", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
        )
        df[col] = pd.to_numeric(cleaned, errors="coerce")
        bad = df[col].isna().sum()
        if bad:
            warnings.append(f"Could not parse {bad} value(s) in '{col}'; treated as 0")
            df[col] = df[col].fillna(0)

    if df.empty:
        raise ValueError(f"No usable order rows in {filename} after cleaning.")

    # Aggregate order-level rows to the canonical per-(sku, date) sales grain.
    aggregated = (
        df.groupby(["sku", "date"], as_index=False)[["units_sold", "revenue_usd"]]
        .sum()
        .sort_values(["sku", "date"])
        .reset_index(drop=True)
    )

    detection = CSVDetection(
        csv_type=fmt.csv_type,
        confidence="high",
        matched_columns=list(mapping.keys()),
        missing_columns=[],
    )
    return CSVParseResult(
        csv_type=fmt.csv_type,
        df=aggregated,
        detection=detection,
        warnings=warnings,
    )


class ERPFormatInfo(TypedDict):
    """Human-readable metadata about one registered ERP format."""

    format_id: str
    name: str
    csv_type: str
    signature_headers: list[str]
    canonical_columns: list[str]


def supported_erp_formats() -> list[ERPFormatInfo]:
    """Human-readable metadata about registered ERP formats."""
    return [
        {
            "format_id": f.format_id,
            "name": f.name,
            "csv_type": f.csv_type,
            "signature_headers": list(f.signature_headers),
            "canonical_columns": sorted(f.column_mapping.keys()),
        }
        for f in ERP_FORMATS
    ]
