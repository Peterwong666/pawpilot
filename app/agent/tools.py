"""Agent tools for PawPilot.

Tools are intentionally stateless and deterministic. They are registered both in the internal
agent runtime and exposed via FastMCP so the same logic serves the API and external MCP clients.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.data.simulated import SimulatedDataStore
from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever


class ToolRegistry:
    """Holds tool definitions and implementations."""

    def __init__(self, retriever: HybridRetriever | None = None) -> None:
        self.settings = get_settings()
        self.retriever = retriever or HybridRetriever()
        self.data_store = SimulatedDataStore()
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
                "description": "Check an Amazon listing draft against style and compliance rules.",
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
                "description": "Query simulated sales/reviews/ads data with DuckDB SQL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "A valid DuckDB SQL query against sales, reviews, or ads tables.",
                        },
                    },
                    "required": ["sql"],
                },
                "handler": self.query_sales_data,
            },
            "analyze_reviews": {
                "description": "Analyze reviews for a SKU and summarize themes.",
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

    async def search_policies(self, query: str) -> list[dict[str, Any]]:
        chunks = await self.retriever.retrieve_texts(query)
        return chunks

    async def check_listing_compliance(self, draft_text: str) -> dict[str, Any]:
        rules = await self.retriever.retrieve_texts(
            "Amazon listing prohibited words style guide title bullet requirements",
            final_top_k=8,
        )
        generator = Generator(provider="deepseek")
        return await generator.check_compliance(draft_text, rules)

    async def query_sales_data(self, sql: str) -> dict[str, Any]:
        df = self.data_store.query(sql)
        return {"rows": df.to_dict(orient="records"), "columns": list(df.columns)}

    async def analyze_reviews(self, sku: str, days: int = 90) -> dict[str, Any]:
        summary = self.data_store.summarize_reviews(sku=sku, days=days)
        knowledge = await self.retriever.retrieve_texts(
            "negative review response SOP review analysis workflow",
            final_top_k=4,
        )
        generator = Generator(provider="deepseek")
        analysis = await generator.analyze_reviews(sku, str(summary), knowledge)
        return {"summary": summary, "analysis": analysis}

    async def get_product_info(self, sku: str) -> dict[str, Any]:
        chunks = await self.retriever.retrieve_texts(
            f"PawPilot {sku} product specification materials certifications care",
            final_top_k=4,
        )
        return {"sku": sku, "chunks": chunks}
