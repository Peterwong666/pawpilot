"""FastMCP server exposing PawPilot tools via the Model Context Protocol.

The same tool logic lives in app.agent.tools; this module only adapts it to the MCP wire
format so Claude Code, Cursor, and other MCP clients can call PawPilot directly.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from app.agent.tools import ToolRegistry

mcp = FastMCP("pawpilot")
registry = ToolRegistry()


@mcp.tool()
async def search_policies(query: str) -> list[dict[str, Any]]:
    """Search Amazon policy and internal SOP documents for a topic."""
    result = await registry.call("search_policies", {"query": query})
    return result.get("result", [])


@mcp.tool()
async def check_listing_compliance(draft_text: str) -> dict[str, Any]:
    """Check an Amazon listing draft against style and compliance rules."""
    return await registry.call("check_listing_compliance", {"draft_text": draft_text})


@mcp.tool()
async def query_sales_data(sql: str) -> dict[str, Any]:
    """Query simulated sales/reviews/ads data with DuckDB SQL."""
    return await registry.call("query_sales_data", {"sql": sql})


@mcp.tool()
async def analyze_reviews(sku: str, days: int = 90) -> dict[str, Any]:
    """Analyze reviews for a SKU and summarize themes."""
    return await registry.call("analyze_reviews", {"sku": sku, "days": days})


@mcp.tool()
async def get_product_info(sku: str) -> dict[str, Any]:
    """Get internal product specifications for a PawPilot SKU."""
    return await registry.call("get_product_info", {"sku": sku})


@mcp.tool()
async def diagnose_sales_anomaly(sku: str, days: int = 14) -> dict[str, Any]:
    """Diagnose why a SKU's units changed: attributes the change to traffic, conversion,
    rating, ads, or price with an evidence chain."""
    return await registry.call("diagnose_sales_anomaly", {"sku": sku, "days": days})


@mcp.tool()
async def analyze_profit(sku: str, price: float | None = None) -> dict[str, Any]:
    """Unit economics for a SKU: referral fee, FBA fee, COGS, margin, break-even price.
    Pass `price` to evaluate a what-if price."""
    arguments: dict[str, Any] = {"sku": sku}
    if price is not None:
        arguments["price"] = price
    return await registry.call("analyze_profit", arguments)


@mcp.tool()
async def check_inventory_health(sku: str | None = None) -> dict[str, Any]:
    """FBA inventory health: days of cover vs replenishment lead time per SKU."""
    arguments: dict[str, Any] = {}
    if sku is not None:
        arguments["sku"] = sku
    return await registry.call("check_inventory_health", arguments)


@mcp.tool()
async def mine_competitor_reviews(product_type: str, top_n: int = 10) -> dict[str, Any]:
    """Mine competitor reviews for a product line ('rope toy', 'harness', 'feeder bowl')
    and aggregate unmet needs (VOC) by theme frequency."""
    return await registry.call(
        "mine_competitor_reviews", {"product_type": product_type, "top_n": top_n}
    )


@mcp.tool()
async def generate_daily_digest() -> dict[str, Any]:
    """Today's operations digest across all SKUs: WoW units, margin, rating, ACOS vs
    target, inventory status, plus deterministic alerts."""
    return await registry.call("generate_daily_digest", {})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
