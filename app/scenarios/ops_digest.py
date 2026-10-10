"""Scenario 4: Daily operations digest (运营日报).

Fixed pipeline, deterministic core:
1. ``generate_daily_digest`` tool computes the portfolio table and alerts in code.
2. Relevant SOP snippets are retrieved for the alert types that fired.
3. The LLM writes only a short Chinese executive summary — every number in the report
   comes from the deterministic layer, never from the LLM.

This is the "proactive monitoring" scenario: the boss opens PawPilot in the morning and
sees what needs handling today, instead of asking questions one by one.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.agent.tools import ToolRegistry
from app.data.hybrid_store import HybridDataStore
from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever

# Alert-type → knowledge-base query used to ground the recommended actions.
_ALERT_KB_QUERIES: dict[str, str] = {
    "sales_drop": "sales decline diagnosis listing ranking traffic conversion",
    "rating_decline": "negative review response SOP account health rating metrics",
    "stockout_risk": "fulfillment inventory basics restock FBA stockout",
    "acos_above_target": "advertising campaign ACOS optimization budget",
}


class OpsDailyDigestScenario:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        generator: Generator | None = None,
        registry: ToolRegistry | None = None,
        provider: str = "deepseek",
        account_id: str = "default",
        marketplace: str = "US",
        use_simulated: bool = True,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or Generator(provider=provider)
        if registry is not None:
            self.registry = registry
        else:
            data_store = HybridDataStore(
                account_id=account_id,
                marketplace=marketplace,
                use_simulated=use_simulated,
            )
            self.registry = ToolRegistry(retriever=self.retriever, data_store=data_store)

    async def generate(self) -> dict[str, Any]:
        digest = await self.registry.generate_daily_digest()

        # Retrieve SOP guidance matching the alert types that actually fired.
        alert_types = {a["type"] for a in digest["alerts"]}
        queries = [_ALERT_KB_QUERIES.get(t, "Amazon operations best practices") for t in sorted(alert_types)]
        knowledge: list[dict[str, Any]] = []
        for query in queries[:3]:  # cap retrievals to keep latency predictable
            knowledge.extend(await self.retriever.retrieve_texts(query, final_top_k=3))

        summary = await self.generator.summarize_ops_digest(digest, knowledge)

        final_answer = self._format_final_answer(digest, summary.get("summary", ""))
        return {
            "final_answer": final_answer,
            "digest": digest,
            "tool_calls": [
                {
                    "id": "generate_daily_digest",
                    "type": "function",
                    "function": {"name": "generate_daily_digest", "arguments": "{}"},
                },
            ],
            "iterations": 1,
            "provider": self.generator.provider,
            "model": self.generator.model,
            "usage": summary.get("usage"),
        }

    @staticmethod
    def _format_final_answer(digest: dict[str, Any], summary: str) -> str:
        lines = [
            f"# 运营日报 — {date.today().isoformat()}",
            "",
            "## 执行摘要",
            "",
            summary.strip(),
            "",
            f"## 告警（{len(digest['alerts'])} 条）",
            "",
        ]
        if digest["alerts"]:
            for a in digest["alerts"]:
                lines.append(
                    f"- **[{a['severity'].upper()}] {a['sku']} — {_ALERT_LABELS.get(a['type'], a['type'])}**："
                    f"{a['detail']}。下一步：{a['action']}"
                )
        else:
            lines.append("- 今日无告警，各项指标健康。")

        lines += [
            "",
            "## 全 SKU 组合概览（近 7 天）",
            "",
            "| SKU | 销量 | 环比 | 收入($) | 毛利率 | 评分(7d) | ACOS | 库存 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for row in digest["sku_rows"]:
            acos = f"{row['acos_7d']}% / 目标 {row['acos_target']}%" if row["acos_7d"] is not None else "无广告"
            lines.append(
                f"| {row['sku']} | {row['units_7d']} | {row['units_wow_pct']:+.1f}% "
                f"| {row['revenue_7d']:.0f} | {row['margin_pct']}% | {row['rating_7d'] or '—'} "
                f"| {acos} | {_STATUS_LABELS.get(row['inventory_status'], row['inventory_status'])} |"
            )
        return "\n".join(lines)


_ALERT_LABELS = {
    "sales_drop": "销量下滑",
    "rating_decline": "评分下降",
    "stockout_risk": "断货风险",
    "acos_above_target": "ACOS 超标",
}

_STATUS_LABELS = {
    "healthy": "健康",
    "low": "偏低",
    "critical": "告急",
    "unknown": "未知",
}
