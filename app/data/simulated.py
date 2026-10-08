"""Generate and query simulated Amazon operational data.

DuckDB is used as an in-process analytical engine so the project can ship with realistic
sales/reviews/ads/costs/inventory/competitor data without requiring a separate warehouse.

The dataset embeds a deterministic "anomaly story" so diagnosis and digest scenarios have
verifiable ground truth:

- PP-RT-102 (flagship rope toy): rating drop driven by durability complaints (last 14 days)
  plus an ad-budget pause (last 10 days) compound into a ~50% unit decline.
- PP-SB-302 (slow feeder bowl): a delayed restock shipment drains FBA inventory to ~15 days
  of cover while the replenishment lead time is 20 days (stockout risk).
- PP-HR-203 (harness): competitor-driven CPC inflation pushes ACOS above the 30% target.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "simulated"

# ---------------------------------------------------------------------------
# Ground-truth anomaly configuration (referenced by tests and scenarios).
# ---------------------------------------------------------------------------
ANOMALY_SALES_SKU = "PP-RT-102"          # units drop: CVR decline + ad pause
ANOMALY_SALES_WINDOW_DAYS = 10           # sales/ads anomaly window (days before end)
ANOMALY_REVIEW_WINDOW_DAYS = 14          # review-quality decline starts earlier
ANOMALY_INVENTORY_SKU = "PP-SB-302"      # stockout risk
ANOMALY_ACOS_SKU = "PP-HR-203"           # ACOS inflation above target
ACOS_TARGET_PCT = 30.0

# ---------------------------------------------------------------------------
# Per-SKU operating parameters.
# ---------------------------------------------------------------------------
_SKU_PARAMS: dict[str, dict[str, Any]] = {
    # price, organic sessions/day, base CVR; campaign SKUs carry ad traffic too.
    "PP-RT-101": {"price": 9.99, "organic_sessions": 85, "cvr": 0.070},
    "PP-RT-102": {
        "price": 14.99, "organic_sessions": 95, "cvr": 0.080,
        "campaign": "RopeToy_Search", "ad_sessions": 55, "cpc": 0.52,
    },
    "PP-RT-103": {"price": 19.99, "organic_sessions": 70, "cvr": 0.065},
    "PP-HR-201": {"price": 12.99, "organic_sessions": 55, "cvr": 0.060},
    "PP-HR-203": {
        "price": 21.99, "organic_sessions": 75, "cvr": 0.072,
        "campaign": "Harness_Search", "ad_sessions": 60, "cpc": 0.68,
    },
    "PP-SB-302": {
        "price": 16.99, "organic_sessions": 110, "cvr": 0.085,
        "campaign": "Bowl_Search", "ad_sessions": 60, "cpc": 0.45,
    },
}

# Unit economics: landed COGS, FBA fulfillment fee, referral fee, restock lead time.
_COSTS: dict[str, dict[str, float]] = {
    "PP-RT-101": {"cogs_usd": 2.10, "fba_fee_usd": 4.32, "referral_fee_pct": 0.15, "restock_lead_time_days": 25},
    "PP-RT-102": {"cogs_usd": 3.20, "fba_fee_usd": 4.86, "referral_fee_pct": 0.15, "restock_lead_time_days": 25},
    "PP-RT-103": {"cogs_usd": 4.50, "fba_fee_usd": 5.26, "referral_fee_pct": 0.15, "restock_lead_time_days": 30},
    "PP-HR-201": {"cogs_usd": 3.80, "fba_fee_usd": 4.65, "referral_fee_pct": 0.15, "restock_lead_time_days": 30},
    "PP-HR-203": {"cogs_usd": 5.90, "fba_fee_usd": 6.18, "referral_fee_pct": 0.15, "restock_lead_time_days": 35},
    "PP-SB-302": {"cogs_usd": 3.40, "fba_fee_usd": 5.09, "referral_fee_pct": 0.15, "restock_lead_time_days": 20},
}

# Review-theme distributions. PP-RT-102 has an anomaly override for recent days.
_REVIEW_THEMES: dict[str, list[tuple[str, float]]] = {
    "PP-RT-101": [("quality", 0.05), ("size", 0.04), ("durability", 0.06), ("positive", 0.85)],
    "PP-RT-102": [("quality", 0.05), ("durability", 0.10), ("positive", 0.85)],
    "PP-RT-103": [("quality", 0.05), ("durability", 0.10), ("positive", 0.85)],
    "PP-HR-201": [("size", 0.10), ("quality", 0.05), ("positive", 0.85)],
    "PP-HR-203": [("size", 0.10), ("rubbing", 0.05), ("positive", 0.85)],
    "PP-SB-302": [("cleaning", 0.10), ("size", 0.05), ("positive", 0.85)],
}
# Anomaly override for PP-RT-102 recent window: durability complaints spike.
_REVIEW_THEMES_ANOMALY: list[tuple[str, float]] = [
    ("quality", 0.05), ("durability", 0.45), ("positive", 0.50),
]

_REVIEW_TEXTS: dict[str, list[str]] = {
    "size": [
        "Runs small. My dog is on the upper end of medium and it is too tight.",
        "Size chart is confusing. Ordered large but it does not fit.",
        "Smaller than expected from the photos.",
    ],
    "rubbing": [
        "The straps rubbed my short-haired dog's skin.",
        "Caused chafing after a long walk.",
    ],
    "cleaning": [
        "Hard to clean between the maze ridges.",
        "Food gets stuck and mold builds up quickly.",
    ],
    "durability": [
        "My power chewer destroyed this in two days.",
        "Frayed quickly. Expected more durable rope.",
        "Not for aggressive chewers despite the claim.",
    ],
    "quality": [
        "Stitching looks cheap.",
        "The rubber ring fell off after one wash.",
    ],
    "positive": [
        "Great quality. My dog loves it.",
        "Perfect size and easy to clean.",
        "Durable and well made.",
        "Exactly as described.",
    ],
}

# Competitor VOC corpus: fictional brands across the three product lines.
_COMPETITOR_LINES: list[dict[str, Any]] = [
    {
        "competitor": "RopeKing",
        "asin": "B0RKING0001",
        "product_type": "rope toy",
        "themes": [
            ("squeaker_failure", 0.22, [
                "The squeaker stopped working after one week.",
                "Squeaker broke on the second day. My dog lost interest immediately.",
            ]),
            ("rubber_smell", 0.16, [
                "Strong chemical rubber smell that would not wash off.",
                "Smells like tires. Had to air it out for days.",
            ]),
            ("fraying", 0.20, [
                "Threads fray everywhere and leave fuzz all over the carpet.",
                "Sheds rope fibers after two play sessions.",
            ]),
            ("size_mismatch", 0.12, [
                "Much thinner than the pictures suggest.",
                "Listed for large dogs but barely fits my beagle's mouth.",
            ]),
            ("positive", 0.30, [
                "My terrier loves the knots and it survived a month so far.",
                "Good value three-pack.",
            ]),
        ],
    },
    {
        "competitor": "PawGear",
        "asin": "B0PWGEAR002",
        "product_type": "harness",
        "themes": [
            ("strap_loosening", 0.24, [
                "The straps loosen during every walk. Retightening constantly.",
                "Buckle slides and my dog backed out of it twice.",
            ]),
            ("buckle_quality", 0.14, [
                "Plastic buckle cracked within a month of light use.",
                "The clasp feels flimsy compared to my old harness.",
            ]),
            ("sizing_confusing", 0.18, [
                "Sizing chart is useless. Ordered per measurements and it still does not fit.",
                "Girth and neck sizing contradict each other.",
            ]),
            ("escape_risk", 0.10, [
                "My husky slipped out of it on the first hike.",
                "Not escape-proof at all despite the claim.",
            ]),
            ("positive", 0.34, [
                "Solid build and the handle on the back is great for traffic.",
                "Fits my poodle perfectly after adjusting once.",
            ]),
        ],
    },
    {
        "competitor": "SlowBite",
        "asin": "B0SLOWBITE03",
        "product_type": "feeder bowl",
        "themes": [
            ("mold_in_ridges", 0.22, [
                "Food traps in the ridges and mold appears within days.",
                "Impossible to clean the grooves fully even with a brush.",
            ]),
            ("slippery_base", 0.18, [
                "Slides across the tile. My dog pushes it around the kitchen.",
                "No grip at all. Needs a mat underneath.",
            ]),
            ("too_easy", 0.12, [
                "My fast eater finishes in two minutes. Maze is too shallow.",
                "Not challenging enough for a motivated lab.",
            ]),
            ("color_fading", 0.08, [
                "Colors faded badly after a few dishwasher runs.",
            ]),
            ("positive", 0.40, [
                "Slowed my golden retriever down from 30 seconds to 4 minutes.",
                "Good quality plastic, no smell, easy wash by hand.",
            ]),
        ],
    },
]

# Allowed tables for the guarded SQL tool.
ALLOWED_TABLES = {"sales", "reviews", "ads", "costs", "inventory", "competitor_reviews"}


def _ensure_data_dir() -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR


def _date_range(n_days: int) -> list[date]:
    """Inclusive daily range ending yesterday, so 'recent window' queries always have data."""
    end = date.today() - timedelta(days=1)
    return [end - timedelta(days=i) for i in range(n_days - 1, -1, -1)]


def _is_anomaly_day(d: date, dates: list[date], window_days: int) -> bool:
    return (dates[-1] - d).days < window_days


def generate_sales_and_ads(
    n_days: int = 90, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate the sales and ads tables in one pass so ad traffic/units stay consistent.

    sales: date, sku, units_sold, price, revenue, sessions, unit_session_pct,
           ad_units, ad_sales_usd (organic units = units_sold - ad_units).
    ads:   date, campaign, sku, spend, sales, acos_pct, impressions, clicks.
    """
    random.seed(seed)
    dates = _date_range(n_days)
    sales_records: list[dict[str, Any]] = []
    ads_records: list[dict[str, Any]] = []

    for idx, d in enumerate(dates):
        weekend_boost = 1.15 if d.weekday() >= 5 else 1.0
        growth = 1.0 + 0.0015 * idx  # mild upward trend over the quarter
        for sku, params in _SKU_PARAMS.items():
            anomaly = sku == ANOMALY_SALES_SKU and _is_anomaly_day(d, dates, ANOMALY_SALES_WINDOW_DAYS)

            # --- Traffic ---------------------------------------------------
            organic_sessions = params["organic_sessions"] * weekend_boost * growth
            organic_sessions *= random.uniform(0.92, 1.08)

            ad_sessions = 0.0
            cpc = float(params.get("cpc", 0.0))
            campaign = params.get("campaign")
            if campaign:
                ad_factor = 0.30 if anomaly else 1.0
                # CPC inflation story for PP-HR-203 (ACOS rises while sales stay flat).
                if sku == ANOMALY_ACOS_SKU and _is_anomaly_day(d, dates, ANOMALY_SALES_WINDOW_DAYS):
                    cpc *= 1.40
                ad_sessions = params["ad_sessions"] * weekend_boost * ad_factor * random.uniform(0.9, 1.1)

            sessions = int(round(organic_sessions + ad_sessions))

            # --- Conversion ------------------------------------------------
            cvr = params["cvr"] * (0.65 if anomaly else 1.0) * random.uniform(0.94, 1.06)
            units = int(round(sessions * cvr))
            ad_units = 0
            if campaign:
                ad_units = min(units, int(round(ad_sessions * cvr * 1.4)))

            price = params["price"]
            revenue = round(units * price, 2)
            ad_sales = round(ad_units * price, 2)

            sales_records.append({
                "date": d.isoformat(),
                "sku": sku,
                "units_sold": units,
                "price": price,
                "revenue": revenue,
                "sessions": sessions,
                "unit_session_pct": round(units / sessions * 100, 2) if sessions else 0.0,
                "ad_units": ad_units,
                "ad_sales_usd": ad_sales,
            })

            if campaign:
                spend = round(ad_sessions * cpc, 2)
                impressions = int(ad_sessions / random.uniform(0.008, 0.018))
                clicks = int(round(ad_sessions))
                ads_records.append({
                    "date": d.isoformat(),
                    "campaign": campaign,
                    "sku": sku,
                    "spend": spend,
                    "sales": ad_sales,
                    "acos_pct": round(spend / ad_sales * 100, 1) if ad_sales else 0.0,
                    "impressions": impressions,
                    "clicks": clicks,
                })

    return pd.DataFrame(sales_records), pd.DataFrame(ads_records)


def generate_reviews(n_days: int = 90, seed: int = 43) -> pd.DataFrame:
    random.seed(seed)
    dates = _date_range(n_days)
    records = []
    review_id = 1000
    for d in dates:
        for sku in _SKU_PARAMS:
            n_reviews = random.randint(1, 3)
            weights = _REVIEW_THEMES[sku]
            if sku == ANOMALY_SALES_SKU and _is_anomaly_day(d, dates, ANOMALY_REVIEW_WINDOW_DAYS):
                weights = _REVIEW_THEMES_ANOMALY
            for _ in range(n_reviews):
                theme = random.choices([w[0] for w in weights], weights=[w[1] for w in weights])[0]
                text = random.choice(_REVIEW_TEXTS[theme])
                if theme == "positive":
                    rating = random.choices([4, 5], weights=[0.3, 0.7])[0]
                elif theme in ("size", "cleaning"):
                    rating = random.choices([3, 2], weights=[0.6, 0.4])[0]
                else:
                    rating = random.choices([3, 2, 1], weights=[0.3, 0.4, 0.3])[0]
                records.append({
                    "review_id": review_id,
                    "date": d.isoformat(),
                    "sku": sku,
                    "rating": rating,
                    "theme": theme,
                    "text": text,
                })
                review_id += 1
    return pd.DataFrame(records)


def generate_costs() -> pd.DataFrame:
    """Static unit-economics reference table."""
    records = [
        {"sku": sku, **{k: v for k, v in cost.items() if k != "restock_lead_time_days"},
         "restock_lead_time_days": int(cost["restock_lead_time_days"])}
        for sku, cost in _COSTS.items()
    ]
    return pd.DataFrame(records)


def generate_inventory(sales_df: pd.DataFrame, n_days: int = 90, seed: int = 45) -> pd.DataFrame:
    """Daily FBA on-hand inventory, depleted by sales and refilled by inbound shipments.

    Normal SKUs run a steady replenishment cadence (healthy cover). PP-SB-302's latest
    shipments are deliberately delayed, leaving ~15 days of cover against a 20-day lead
    time (stockout-risk story).
    """
    random.seed(seed)
    dates = _date_range(n_days)
    records = []
    units_lookup = {
        (row["date"], row["sku"]): row["units_sold"] for _, row in sales_df.iterrows()
    }
    for sku in _SKU_PARAMS:
        # Average daily units from the actual sales table (organic + ad), so depletion
        # matches real demand instead of an organic-only estimate.
        avg_daily = sales_df[sales_df["sku"] == sku]["units_sold"].mean()
        on_hand = int(70 * avg_daily)
        # Steady cadence: a ~20-day supply arrives every 20 days.
        inbound_schedule = {i: int(20 * avg_daily) for i in range(20, n_days, 20)}
        if sku == ANOMALY_INVENTORY_SKU:
            # Delayed-shipment story: only two early restocks, nothing recent.
            on_hand = int(65 * avg_daily)
            inbound_schedule = {25: int(20 * avg_daily), 55: int(20 * avg_daily)}
        for i, d in enumerate(dates):
            inbound_today = inbound_schedule.get(i, 0)
            on_hand = max(0, on_hand - units_lookup.get((d.isoformat(), sku), 0)) + inbound_today
            records.append({
                "date": d.isoformat(),
                "sku": sku,
                "fba_on_hand_units": on_hand,
                "inbound_units": inbound_today,
            })
    return pd.DataFrame(records)


def generate_competitor_reviews(n_days: int = 90, seed: int = 46) -> pd.DataFrame:
    """Simulated competitor product reviews used for VOC-driven product development."""
    random.seed(seed)
    dates = _date_range(n_days)
    records = []
    review_id = 5000
    for line in _COMPETITOR_LINES:
        for d in dates:
            n_reviews = random.randint(0, 2)
            for _ in range(n_reviews):
                themes = line["themes"]
                theme, _, texts = random.choices(themes, weights=[t[1] for t in themes])[0]
                text = random.choice(texts)
                if theme == "positive":
                    rating = random.choices([4, 5], weights=[0.35, 0.65])[0]
                else:
                    rating = random.choices([3, 2, 1], weights=[0.2, 0.45, 0.35])[0]
                records.append({
                    "review_id": review_id,
                    "date": d.isoformat(),
                    "competitor": line["competitor"],
                    "asin": line["asin"],
                    "product_type": line["product_type"],
                    "rating": rating,
                    "theme": theme,
                    "text": text,
                })
                review_id += 1
    return pd.DataFrame(records)


def build_simulated_data(overwrite: bool = False) -> dict[str, Path]:
    """Generate CSV files under data/simulated if they do not exist."""
    _ensure_data_dir()
    sales_df, ads_df = generate_sales_and_ads()
    frames: dict[str, pd.DataFrame] = {
        "sales": sales_df,
        "ads": ads_df,
        "reviews": generate_reviews(),
        "costs": generate_costs(),
        "inventory": generate_inventory(sales_df),
        "competitor_reviews": generate_competitor_reviews(),
    }
    paths: dict[str, Path] = {}
    for name, df in frames.items():
        path = _DATA_DIR / f"{name}.csv"
        if overwrite or not path.exists():
            df.to_csv(path, index=False)
        paths[name] = path
    return paths


class SimulatedDataStore:
    """DuckDB-backed in-memory store for operational queries."""

    _instance: SimulatedDataStore | None = None

    def __init__(self) -> None:
        self.con = duckdb.connect(":memory:")
        self._load()

    def _load(self) -> None:
        paths = build_simulated_data()
        for name in ALLOWED_TABLES:
            self.con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_csv_auto('{paths[name]}')")

    def query(self, sql: str) -> pd.DataFrame:
        return self.con.execute(sql).fetchdf()

    def summarize_reviews(self, sku: str | None = None, days: int = 90) -> dict[str, Any]:
        where = f"WHERE date >= CURRENT_DATE - INTERVAL '{days} days'"
        if sku:
            where += f" AND sku = '{sku}'"
        df = self.query(f"""
            SELECT theme, COUNT(*) as count, AVG(rating) as avg_rating
            FROM reviews
            {where}
            GROUP BY theme
            ORDER BY count DESC
        """)
        return df.to_dict(orient="records")
