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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
