"""Agent tools for PawPilot.

Tools are intentionally stateless and deterministic: business logic (anomaly
attribution, margin math, inventory cover, VOC aggregation, alert rules) lives in
plain Python so it is testable and auditable, while the LLM only narrates results.

They are registered both in the internal agent runtime and exposed via FastMCP so
the same logic serves the API and external MCP clients.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.config import get_settings
from app.data.simulated import ACOS_TARGET_PCT, ALLOWED_TABLES, SimulatedDataStore
from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever
from app.scenarios.compliance_engine import ComplianceRuleEngine

# Read-only SQL guard configuration.
_SQL_START_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_SQL_FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|export|import|pragma|grant|revoke|set|call|checkpoint)\b",
    re.IGNORECASE,
)
_SQL_TABLE_RE = re.compile(r"\b(" + "|".join(sorted(ALLOWED_TABLES)) + r")\b", re.IGNORECASE)
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Severity thresholds shared by the diagnosis tool and the daily digest.
UNITS_DROP_ALERT_PCT = -20.0
RATING_ALERT_LEVEL = 4.0
RATING_ALERT_DROP = 0.3
ACOS_ALERT_PCT = ACOS_TARGET_PCT + 5


def validate_readonly_sql(sql: str) -> str | None:
    """Return an error message if the SQL is not a single read-only allowlisted query."""
    stripped = sql.strip()
    if not stripped:
        return "Empty SQL query."
    if not _SQL_START_RE.match(stripped):
        return "Only SELECT / WITH queries are allowed (read-only tool)."
    if ";" in stripped:
        return "Multiple statements are not allowed."
    forbidden = _SQL_FORBIDDEN_RE.search(stripped)
    if forbidden:
        return f"Forbidden keyword in read-only query: '{forbidden.group(0)}'."
    if not _SQL_TABLE_RE.search(stripped):
        return f"Query must reference at least one allowed table: {sorted(ALLOWED_TABLES)}."
    return None


def _safe_identifier(value: str, kind: str) -> str:
    """Reject values that could break out of SQL string interpolation."""
    if not _SQL_IDENTIFIER_RE.match(value):
        msg = f"Invalid {kind}: {value!r}"
        raise ValueError(msg)
    return value


class ToolRegistry:
    """Holds tool definitions and implementations."""

    def __init__(self, retriever: HybridRetriever | None = None) -> None:
        self.settings = get_settings()
        self.retriever = retriever or HybridRetriever()
        self.data_store = SimulatedDataStore()
        self.rule_engine = ComplianceRuleEngine()
        self._tools: dict[str, dict[str, Any]] = {
            "search_policies": {
                "description": "Search Amazon policy and internal SOP documents for a topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The policy or SOP topic to search for.",
                        },
                    },
                    "required": ["query"],
                },
                "handler": self.search_policies,
            },
            "check_listing_compliance": {
                "description": (
                    "Check an Amazon listing draft with a hybrid engine: deterministic rules "
                    "(prohibited words, structure limits) plus an LLM semantic review."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "draft_text": {
                            "type": "string",
                            "description": "The full listing text (title, bullets, description, keywords).",
                        },
                    },
                    "required": ["draft_text"],
                },
                "handler": self.check_listing_compliance,
            },
            "query_sales_data": {
                "description": "Query simulated sales/reviews/ads/costs/inventory data with read-only DuckDB SQL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": (
                                "A read-only DuckDB SELECT query against the sales, reviews, ads, "
                                "costs, inventory, or competitor_reviews tables."
                            ),
                        },
                    },
                    "required": ["sql"],
                },
                "handler": self.query_sales_data,
            },
            "analyze_reviews": {
                "description": "Analyze reviews for a SKU: theme distribution plus rating trend.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sku": {
                            "type": "string",
                            "description": "Product SKU, e.g. PP-RT-102.",
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of recent days to include.",
                            "default": 90,
                        },
                    },
                    "required": ["sku"],
                },
                "handler": self.analyze_reviews,
            },
            "get_product_info": {
                "description": "Get internal product specifications for a PawPilot SKU.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sku": {
                            "type": "string",
                            "description": "Product SKU.",
                        },
                    },
                    "required": ["sku"],
                },
                "handler": self.get_product_info,
            },
            "diagnose_sales_anomaly": {
                "description": (
                    "Diagnose why a SKU's units rose or fell: compares the recent window with the "
                    "previous one and attributes the change to traffic, conversion, rating, ads, or price."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string", "description": "Product SKU, e.g. PP-RT-102."},
                        "days": {
                            "type": "integer",
                            "description": "Window size in days (recent vs previous window).",
                            "default": 14,
                        },
                    },
                    "required": ["sku"],
                },
                "handler": self.diagnose_sales_anomaly,
            },
            "analyze_profit": {
                "description": (
                    "Unit economics for a SKU: referral fee, FBA fee, COGS, margin, break-even price. "
                    "Optionally evaluate a what-if price."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string", "description": "Product SKU."},
                        "price": {
                            "type": "number",
                            "description": "Optional what-if price; defaults to the current price.",
                        },
                    },
                    "required": ["sku"],
                },
                "handler": self.analyze_profit,
            },
            "check_inventory_health": {
                "description": (
                    "FBA inventory health per SKU: days of cover vs replenishment lead time and "
                    "the latest date a restock order should be placed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sku": {
                            "type": "string",
                            "description": "Optional SKU; omit to check all SKUs.",
                        },
                    },
                },
                "handler": self.check_inventory_health,
            },
            "mine_competitor_reviews": {
                "description": (
                    "Mine competitor reviews for a product line and aggregate unmet needs "
                    "(VOC) by theme frequency for product development."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_type": {
                            "type": "string",
                            "description": "Product line: 'rope toy', 'harness', or 'feeder bowl'.",
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "Max themes to return.",
                            "default": 10,
                        },
                    },
                    "required": ["product_type"],
                },
                "handler": self.mine_competitor_reviews,
            },
            "generate_daily_digest": {
                "description": (
                    "Generate today's operations digest across all SKUs: WoW units, revenue, margin, "
                    "rating, ACOS vs target, inventory status, plus deterministic alerts."
                ),
                "parameters": {"type": "object", "properties": {}},
                "handler": self.generate_daily_digest,
            },
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec["description"],
                    "parameters": spec["parameters"],
                },
            }
            for name, spec in self._tools.items()
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            return {"error": f"Unknown tool: {name}"}
        try:
            result = await self._tools[name]["handler"](**arguments)
            return {"tool": name, "result": result}
        except Exception as exc:
            return {"tool": name, "error": str(exc)}

    # ------------------------------------------------------------------
    # Knowledge-base tools
    # ------------------------------------------------------------------
    async def search_policies(self, query: str) -> list[dict[str, Any]]:
        chunks = await self.retriever.retrieve_texts(query)
        return chunks

    async def check_listing_compliance(self, draft_text: str) -> dict[str, Any]:
        """Hybrid compliance check: deterministic rule engine + LLM semantic review."""
        rule_issues = self.rule_engine.check_draft(draft_text)
        rules = await self.retriever.retrieve_texts(
            "Amazon listing prohibited words style guide title bullet requirements",
            final_top_k=8,
        )
        generator = Generator(provider="deepseek")
        llm_result = await generator.check_compliance(draft_text, rules)
        llm_compliance = llm_result.get("compliance", {})
        critical = sum(
            1 for i in rule_issues if i.get("severity") == "critical"
        ) + sum(
            1
            for i in (llm_compliance.get("issues") or [])
            if isinstance(i, dict) and str(i.get("severity", "")).lower() in ("critical", "high")
        )
        return {
            "passed": critical == 0,
            "rule_issues": rule_issues,
            "llm_compliance": llm_compliance,
            "usage": llm_result.get("usage"),
        }

    # ------------------------------------------------------------------
    # Data tools
    # ------------------------------------------------------------------
    async def query_sales_data(self, sql: str) -> dict[str, Any]:
        error = validate_readonly_sql(sql)
        if error:
            return {"error": error}
        df = self.data_store.query(sql)
        return {"rows": df.to_dict(orient="records"), "columns": list(df.columns)}

    async def analyze_reviews(self, sku: str, days: int = 90) -> dict[str, Any]:
        sku = _safe_identifier(sku, "SKU")
        summary = self.data_store.summarize_reviews(sku=sku, days=days)
        rating = self.data_store.query(f"""
            SELECT
              AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '{int(days)} days' THEN rating END) AS cur,
              AVG(CASE WHEN date < CURRENT_DATE - INTERVAL '{int(days)} days'
                        AND date >= CURRENT_DATE - INTERVAL '{int(days) * 2} days' THEN rating END) AS prev
            FROM reviews WHERE sku = '{sku}'
        """).to_dict(orient="records")[0]
        cur = float(rating["cur"] or 0.0)
        prev = float(rating["prev"] or 0.0)
        overall = {
            "avg_rating_current_window": round(cur, 2),
            "avg_rating_previous_window": round(prev, 2),
            "rating_change": round(cur - prev, 2),
        }
        knowledge = await self.retriever.retrieve_texts(
            "negative review response SOP review analysis workflow",
            final_top_k=4,
        )
        generator = Generator(provider="deepseek")
        analysis = await generator.analyze_reviews(sku, str({"summary": summary, "overall": overall}), knowledge)
        return {"summary": summary, "overall": overall, "analysis": analysis}

    async def get_product_info(self, sku: str) -> dict[str, Any]:
        sku = _safe_identifier(sku, "SKU")
        chunks = await self.retriever.retrieve_texts(
            f"PawPilot {sku} product specification materials certifications care",
            final_top_k=4,
        )
        return {"sku": sku, "chunks": chunks}

    # ------------------------------------------------------------------
    # Deterministic analytics tools (FDE core: logic in code, LLM narrates)
    # ------------------------------------------------------------------
    async def diagnose_sales_anomaly(self, sku: str, days: int = 14) -> dict[str, Any]:
        """Attribute a SKU's unit change to traffic / conversion / rating / ads / price."""
        sku = _safe_identifier(sku, "SKU")
        days = int(days)

        def window_sql(start_offset: int) -> str:
            return f"""
                SELECT
                  SUM(units_sold) AS units, SUM(sessions) AS sessions,
                  AVG(unit_session_pct) AS cvr, AVG(price) AS price,
                  SUM(ad_sales_usd) AS ad_sales,
                  (SELECT COALESCE(SUM(spend), 0) FROM ads
                    WHERE sku = '{sku}'
                      AND date < CURRENT_DATE - INTERVAL '{start_offset} days'
                      AND date >= CURRENT_DATE - INTERVAL '{start_offset + days} days') AS ad_spend,
                  (SELECT COALESCE(AVG(rating), 0) FROM reviews
                    WHERE sku = '{sku}'
                      AND date < CURRENT_DATE - INTERVAL '{start_offset} days'
                      AND date >= CURRENT_DATE - INTERVAL '{start_offset + days} days') AS avg_rating
                FROM sales
                WHERE sku = '{sku}'
                  AND date < CURRENT_DATE - INTERVAL '{start_offset} days'
                  AND date >= CURRENT_DATE - INTERVAL '{start_offset + days} days'
            """

        cur = self.data_store.query(window_sql(0)).to_dict(orient="records")[0]
        prev = self.data_store.query(window_sql(days)).to_dict(orient="records")[0]

        def rel(cur_v: float, prev_v: float) -> float:
            return (cur_v - prev_v) / prev_v * 100 if prev_v else 0.0

        units_change = rel(float(cur["units"] or 0), float(prev["units"] or 0))
        sessions_change = rel(float(cur["sessions"] or 0), float(prev["sessions"] or 0))
        cvr_change = rel(float(cur["cvr"] or 0), float(prev["cvr"] or 0))
        price_change = rel(float(cur["price"] or 0), float(prev["price"] or 0))
        ad_spend_change = rel(float(cur["ad_spend"] or 0), float(prev["ad_spend"] or 0))
        rating_change = float(cur["avg_rating"] or 0) - float(prev["avg_rating"] or 0)

        metrics = {
            "current": {k: (round(float(v), 2) if v is not None else None) for k, v in cur.items()},
            "previous": {k: (round(float(v), 2) if v is not None else None) for k, v in prev.items()},
            "change_pct": {
                "units": round(units_change, 1),
                "sessions": round(sessions_change, 1),
                "cvr": round(cvr_change, 1),
                "price": round(price_change, 1),
                "ad_spend": round(ad_spend_change, 1),
                "rating_change": round(rating_change, 2),
            },
        }

        if units_change > UNITS_DROP_ALERT_PCT:
            return {
                "sku": sku,
                "window_days": days,
                "status": "normal",
                "metrics": metrics,
                "suspected_causes": [],
                "recommended_next_steps": ["No significant unit decline detected in this window."],
            }

        causes: list[dict[str, Any]] = []
        if sessions_change <= -15 and ad_spend_change <= -30:
            causes.append({
                "cause": "ad_budget_cut",
                "evidence": f"sessions {sessions_change:.1f}% with ad spend {ad_spend_change:.1f}%",
                "confidence": "high",
            })
        elif sessions_change <= -15:
            causes.append({
                "cause": "organic_traffic_drop",
                "evidence": f"sessions {sessions_change:.1f}% while ad spend {ad_spend_change:.1f}%",
                "confidence": "medium",
            })
        if cvr_change <= -15 and rating_change <= -RATING_ALERT_DROP:
            causes.append({
                "cause": "rating_decline",
                "evidence": f"CVR {cvr_change:.1f}% with rating {rating_change:+.2f}",
                "confidence": "high",
            })
        elif cvr_change <= -15:
            causes.append({
                "cause": "conversion_drop",
                "evidence": f"CVR {cvr_change:.1f}% with stable rating ({float(cur['avg_rating'] or 0):.2f})",
                "confidence": "medium",
            })
        if abs(price_change) >= 5:
            causes.append({
                "cause": "price_change",
                "evidence": f"price {price_change:+.1f}%",
                "confidence": "medium",
            })

        next_steps: list[str] = []
        for c in causes:
            next_steps.extend(_CAUSE_PLAYBOOK[c["cause"]])

        return {
            "sku": sku,
            "window_days": days,
            "status": "anomaly_detected",
            "metrics": metrics,
            "suspected_causes": causes,
            "recommended_next_steps": next_steps,
        }

    async def analyze_profit(self, sku: str, price: float | None = None) -> dict[str, Any]:
        """Unit economics: fees, margin, break-even, plus a 30-day profit estimate."""
        sku = _safe_identifier(sku, "SKU")
        cost = self.data_store.query(
            f"SELECT * FROM costs WHERE sku = '{sku}'"
        ).to_dict(orient="records")
        if not cost:
            msg = f"Unknown SKU: {sku}"
            raise ValueError(msg)
        cost = cost[0]
        current = self.data_store.query(f"""
            SELECT price FROM sales WHERE sku = '{sku}'
            ORDER BY date DESC LIMIT 1
        """).to_dict(orient="records")
        if not current:
            msg = f"No sales data for SKU: {sku}"
            raise ValueError(msg)
        effective_price = float(price) if price is not None else float(current[0]["price"])
        if effective_price <= 0:
            msg = "Price must be positive."
            raise ValueError(msg)

        referral_fee = round(effective_price * float(cost["referral_fee_pct"]), 2)
        fba_fee = round(float(cost["fba_fee_usd"]), 2)
        cogs = round(float(cost["cogs_usd"]), 2)
        margin = round(effective_price - referral_fee - fba_fee - cogs, 2)
        margin_pct = round(margin / effective_price * 100, 1)
        break_even = round((fba_fee + cogs) / (1 - float(cost["referral_fee_pct"])), 2)

        avg_units = self.data_store.query(f"""
            SELECT AVG(units_sold) AS u FROM sales
            WHERE sku = '{sku}' AND date >= CURRENT_DATE - INTERVAL '30 days'
        """).to_dict(orient="records")[0]
        daily_units = float(avg_units["u"] or 0)

        return {
            "sku": sku,
            "price": round(effective_price, 2),
            "what_if_price": price is not None,
            "fees": {
                "referral_fee": referral_fee,
                "fba_fulfillment_fee": fba_fee,
                "cogs_landed": cogs,
            },
            "margin_per_unit": margin,
            "margin_pct": margin_pct,
            "break_even_price": break_even,
            "avg_daily_units_30d": round(daily_units, 1),
            "est_monthly_profit": round(margin * daily_units * 30, 2),
        }

    async def check_inventory_health(self, sku: str | None = None) -> dict[str, Any]:
        """Days of cover vs lead time; flags SKUs that must be reordered now."""
        sku_filter = f"AND i.sku = '{_safe_identifier(sku, 'SKU')}'" if sku else ""
        rows = self.data_store.query(f"""
            SELECT i.sku,
                   i.fba_on_hand_units AS on_hand,
                   c.restock_lead_time_days AS lead_time_days,
                   (SELECT AVG(units_sold) FROM sales s
                     WHERE s.sku = i.sku AND s.date >= CURRENT_DATE - INTERVAL '7 days') AS avg_daily
            FROM inventory i
            JOIN costs c ON c.sku = i.sku
            WHERE i.date = (SELECT MAX(date) FROM inventory)
            {sku_filter}
            ORDER BY i.sku
        """).to_dict(orient="records")

        results = []
        for row in rows:
            avg_daily = float(row["avg_daily"] or 0)
            on_hand = float(row["on_hand"] or 0)
            cover = on_hand / avg_daily if avg_daily > 0 else 999.0
            lead = float(row["lead_time_days"])
            if cover < lead:
                status = "critical"
            elif cover < lead + 14:
                status = "low"
            else:
                status = "healthy"
            results.append({
                "sku": row["sku"],
                "fba_on_hand_units": int(on_hand),
                "avg_daily_units_7d": round(avg_daily, 1),
                "days_of_cover": round(cover, 1),
                "restock_lead_time_days": int(lead),
                "must_order_within_days": round(cover - lead, 1),
                "status": status,
            })
        return {"skus": results}

    async def mine_competitor_reviews(self, product_type: str, top_n: int = 10) -> dict[str, Any]:
        """Aggregate competitor VOC by theme frequency for product development."""
        product_type = product_type.strip().lower()
        valid = self.data_store.query(
            "SELECT DISTINCT product_type FROM competitor_reviews"
        ).to_dict(orient="records")
        valid_types = {r["product_type"] for r in valid}
        if product_type not in valid_types:
            msg = f"Unknown product_type {product_type!r}. Valid values: {sorted(valid_types)}"
            raise ValueError(msg)

        meta = self.data_store.query(f"""
            SELECT competitor, asin, COUNT(*) AS n, AVG(rating) AS avg_rating
            FROM competitor_reviews WHERE product_type = '{product_type}'
            GROUP BY competitor, asin
        """).to_dict(orient="records")
        themes = self.data_store.query(f"""
            SELECT theme, COUNT(*) AS count,
                   AVG(rating) AS avg_rating,
                   SUM(CASE WHEN rating <= 3 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS negative_share_pct
            FROM competitor_reviews WHERE product_type = '{product_type}'
            GROUP BY theme ORDER BY count DESC
        """).to_dict(orient="records")

        result_themes = []
        for theme_row in themes[:top_n]:
            samples = self.data_store.query(f"""
                SELECT text FROM competitor_reviews
                WHERE product_type = '{product_type}' AND theme = '{theme_row['theme']}'
                ORDER BY random() LIMIT 2
            """).to_dict(orient="records")
            result_themes.append({
                "theme": theme_row["theme"],
                "count": int(theme_row["count"]),
                "negative_share_pct": round(float(theme_row["negative_share_pct"]), 1),
                "avg_rating": round(float(theme_row["avg_rating"]), 2),
                "sample_quotes": [s["text"] for s in samples],
            })
        return {
            "product_type": product_type,
            "competitors": [
                {"competitor": m["competitor"], "asin": m["asin"],
                 "reviews": int(m["n"]), "avg_rating": round(float(m["avg_rating"]), 2)}
                for m in meta
            ],
            "total_reviews": int(sum(m["count"] for m in themes)),
            "themes": result_themes,
        }

    async def generate_daily_digest(self) -> dict[str, Any]:
        """Portfolio-level daily digest with deterministic alert rules."""
        skus = self.data_store.query(
            "SELECT DISTINCT sku FROM sales ORDER BY sku"
        ).to_dict(orient="records")
        inventory = {
            r["sku"]: r
            for r in (await self.check_inventory_health())["skus"]
        }

        sku_rows = []
        alerts: list[dict[str, Any]] = []
        for row in skus:
            sku = row["sku"]
            m = self.data_store.query(f"""
                SELECT
                  SUM(CASE WHEN date >= CURRENT_DATE - INTERVAL '7 days' THEN units_sold ELSE 0 END) AS units_7d,
                  SUM(CASE WHEN date < CURRENT_DATE - INTERVAL '7 days'
                            AND date >= CURRENT_DATE - INTERVAL '14 days' THEN units_sold ELSE 0 END) AS units_prev_7d,
                  SUM(CASE WHEN date >= CURRENT_DATE - INTERVAL '7 days' THEN revenue ELSE 0 END) AS revenue_7d,
                  AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '7 days' THEN price END) AS avg_price
                FROM sales WHERE sku = '{sku}'
            """).to_dict(orient="records")[0]
            rating = self.data_store.query(f"""
                SELECT
                  AVG(CASE WHEN date >= CURRENT_DATE - INTERVAL '7 days' THEN rating END) AS cur,
                  AVG(CASE WHEN date < CURRENT_DATE - INTERVAL '7 days'
                            AND date >= CURRENT_DATE - INTERVAL '14 days' THEN rating END) AS prev
                FROM reviews WHERE sku = '{sku}'
            """).to_dict(orient="records")[0]
            acos = self.data_store.query(f"""
                SELECT SUM(spend) AS spend, SUM(sales) AS sales FROM ads
                WHERE sku = '{sku}' AND date >= CURRENT_DATE - INTERVAL '7 days'
            """).to_dict(orient="records")[0]
            profit = await self.analyze_profit(sku)

            units_7d = float(m["units_7d"] or 0)
            units_prev = float(m["units_prev_7d"] or 0)
            wow = (units_7d - units_prev) / units_prev * 100 if units_prev else 0.0
            acos_7d = (
                round(float(acos["spend"]) / float(acos["sales"]) * 100, 1)
                if float(acos["sales"] or 0) > 0
                else None
            )
            rating_cur = round(float(rating["cur"] or 0), 2)
            rating_prev = round(float(rating["prev"] or 0), 2)
            inv = inventory.get(sku, {})

            sku_rows.append({
                "sku": sku,
                "units_7d": int(units_7d),
                "units_wow_pct": round(wow, 1),
                "revenue_7d": round(float(m["revenue_7d"] or 0), 2),
                "margin_pct": profit["margin_pct"],
                "est_profit_7d": round(profit["margin_per_unit"] * units_7d, 2),
                "rating_7d": rating_cur,
                "rating_prev_7d": rating_prev,
                "acos_7d": acos_7d,
                "acos_target": ACOS_TARGET_PCT,
                "inventory_status": inv.get("status", "unknown"),
                "days_of_cover": inv.get("days_of_cover"),
            })

            if wow <= UNITS_DROP_ALERT_PCT:
                alerts.append({
                    "type": "sales_drop",
                    "sku": sku,
                    "severity": "high",
                    "detail": f"units {wow:+.1f}% WoW ({int(units_prev)} -> {int(units_7d)})",
                    "action": "Run diagnose_sales_anomaly to attribute the decline.",
                })
            if acos_7d is not None and acos_7d > ACOS_ALERT_PCT:
                alerts.append({
                    "type": "acos_above_target",
                    "sku": sku,
                    "severity": "medium",
                    "detail": f"ACOS {acos_7d}% vs target {ACOS_TARGET_PCT}% (7-day)",
                    "action": "Review bids and search-term report; check for CPC inflation.",
                })
            if rating_cur and (rating_cur < RATING_ALERT_LEVEL or (rating_prev and rating_prev - rating_cur > RATING_ALERT_DROP)):
                alerts.append({
                    "type": "rating_decline",
                    "sku": sku,
                    "severity": "high",
                    "detail": f"rating {rating_prev} -> {rating_cur} (7-day avg)",
                    "action": "Analyze review themes and apply the negative-review SOP.",
                })
            if inv.get("status") in ("critical", "low"):
                alerts.append({
                    "type": "stockout_risk",
                    "sku": sku,
                    "severity": "high" if inv.get("status") == "critical" else "medium",
                    "detail": (
                        f"{inv.get('days_of_cover')} days of cover vs "
                        f"{inv.get('restock_lead_time_days')}-day lead time"
                    ),
                    "action": "Place a restock order now; expedite if critical.",
                })

        return {
            "sku_rows": sku_rows,
            "alerts": alerts,
            "alert_count": len(alerts),
            "acos_target_pct": ACOS_TARGET_PCT,
        }


_CAUSE_PLAYBOOK: dict[str, list[str]] = {
    "ad_budget_cut": [
        "Confirm whether the ad pause was intentional (budget cycle vs performance action).",
        "Check campaign ACOS trend before restoring spend; restart at reduced bids.",
    ],
    "organic_traffic_drop": [
        "Check keyword ranking and buy-box share for the top search terms.",
        "Verify the listing is not suppressed (title/keyword policy compliance).",
    ],
    "rating_decline": [
        "Run analyze_reviews to identify the top complaint theme.",
        "Apply the negative-review response SOP templates; assess removal eligibility.",
    ],
    "conversion_drop": [
        "Compare price and main image against the top three competitors.",
        "A/B test the first bullet and main image for conversion lift.",
    ],
    "price_change": [
        "Validate the price change against the margin target (analyze_profit).",
    ],
}
