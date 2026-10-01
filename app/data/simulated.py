"""Generate and query simulated Amazon operational data.

DuckDB is used as an in-process analytical engine so the project can ship with realistic
sales/reviews/ads data without requiring a separate data warehouse.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "simulated"


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _random_date_range(days: int = 90) -> list[date]:
    end = date(2026, 9, 30)
    return [end - timedelta(days=i) for i in range(days - 1, -1, -1)]


def generate_sales(n_days: int = 90, seed: int = 42) -> pd.DataFrame:
    random.seed(seed)
    dates = _random_date_range(n_days)
    skus = ["PP-RT-101", "PP-RT-102", "PP-RT-103", "PP-HR-201", "PP-HR-203", "PP-SB-302"]
    records = []
    for d in dates:
        for sku in skus:
            base = {"PP-RT-101": 8, "PP-RT-102": 12, "PP-RT-103": 10,
                    "PP-HR-201": 5, "PP-HR-203": 9, "PP-SB-302": 15}[sku]
            noise = random.randint(-3, 4)
            units = max(0, base + noise)
            price = {"PP-RT-101": 9.99, "PP-RT-102": 14.99, "PP-RT-103": 19.99,
                     "PP-HR-201": 12.99, "PP-HR-203": 21.99, "PP-SB-302": 16.99}[sku]
            records.append({
                "date": d.isoformat(),
                "sku": sku,
                "units_sold": units,
                "price": price,
                "revenue": round(units * price, 2),
            })
    return pd.DataFrame(records)


def generate_reviews(n_days: int = 90, seed: int = 43) -> pd.DataFrame:
    random.seed(seed)
    dates = _random_date_range(n_days)
    skus = ["PP-RT-101", "PP-RT-102", "PP-RT-103", "PP-HR-201", "PP-HR-203", "PP-SB-302"]
    themes = {
        "PP-RT-101": [("quality", 0.15), ("size", 0.10), ("durability", 0.25), ("positive", 0.50)],
        "PP-RT-103": [("quality", 0.10), ("size", 0.05), ("durability", 0.35), ("positive", 0.50)],
        "PP-HR-201": [("size", 0.40), ("quality", 0.10), ("positive", 0.50)],
        "PP-HR-203": [("size", 0.30), ("rubbing", 0.15), ("positive", 0.55)],
        "PP-SB-302": [("cleaning", 0.25), ("size", 0.15), ("positive", 0.60)],
        "PP-RT-102": [("quality", 0.10), ("durability", 0.20), ("positive", 0.70)],
    }
    sample_texts = {
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
    records = []
    review_id = 1000
    for d in dates:
        for sku in skus:
            n_reviews = random.randint(0, 3)
            weights = themes[sku]
            for _ in range(n_reviews):
                theme = random.choices([w[0] for w in weights], weights=[w[1] for w in weights])[0]
                text = random.choice(sample_texts[theme])
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


def generate_ads(n_days: int = 90, seed: int = 44) -> pd.DataFrame:
    random.seed(seed)
    dates = _random_date_range(n_days)
    campaigns = [
        {"name": "RopeToy_Search", "sku": "PP-RT-102"},
        {"name": "Harness_Search", "sku": "PP-HR-203"},
        {"name": "Bowl_Search", "sku": "PP-SB-302"},
    ]
    records = []
    for d in dates:
        for camp in campaigns:
            spend = round(random.uniform(15, 55), 2)
            sales = round(spend * random.uniform(1.8, 5.5), 2)
            impressions = random.randint(1500, 6000)
            clicks = max(1, int(impressions * random.uniform(0.005, 0.035)))
            records.append({
                "date": d.isoformat(),
                "campaign": camp["name"],
                "sku": camp["sku"],
                "spend": spend,
                "sales": sales,
                "acos_pct": round(spend / sales * 100, 1) if sales else 0.0,
                "impressions": impressions,
                "clicks": clicks,
            })
    return pd.DataFrame(records)


def build_simulated_data(overwrite: bool = False) -> dict[str, Path]:
    """Generate CSV files under data/simulated if they do not exist."""
    _ensure_data_dir()
    paths = {}
    for name, generator in [("sales", generate_sales), ("reviews", generate_reviews), ("ads", generate_ads)]:
        path = _DATA_DIR / f"{name}.csv"
        if overwrite or not path.exists():
            df = generator()
            df.to_csv(path, index=False)
        paths[name] = path
    return paths


class SimulatedDataStore:
    """DuckDB-backed in-memory store for operational queries."""

    def __init__(self) -> None:
        self.con = duckdb.connect(":memory:")
        self._load()

    def _load(self) -> None:
        paths = build_simulated_data()
        self.con.execute(f"CREATE TABLE sales AS SELECT * FROM read_csv_auto('{paths['sales']}')")
        self.con.execute(f"CREATE TABLE reviews AS SELECT * FROM read_csv_auto('{paths['reviews']}')")
        self.con.execute(f"CREATE TABLE ads AS SELECT * FROM read_csv_auto('{paths['ads']}')")

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
