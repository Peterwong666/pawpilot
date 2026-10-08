"""Scenario 5: Sales anomaly diagnosis (销量异动诊断).

Answers the boss's first question when a SKU drops: "为什么掉量？"

Fixed pipeline, deterministic core:
1. ``diagnose_sales_anomaly`` compares the recent window with the previous one and
   attributes the change (traffic / conversion / rating / ads / price) in code.
2. SOP guidance is retrieved for the specific suspected causes.
3. The LLM narrates the evidence chain in Chinese — all numbers come from the
   deterministic diagnosis, so the story is reproducible and auditable.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.tools import ToolRegistry
from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever

_CAUSE_KB_QUERIES: dict[str, str] = {
    "ad_budget_cut": "advertising campaign budget ACOS optimization restart bids",
    "organic_traffic_drop": "listing suppression search ranking policy keyword",
    "rating_decline": "negative review response SOP account health rating metrics",
    "conversion_drop": "listing quality checklist conversion main image price",
    "price_change": "pricing profit margin break-even analysis",
}


class SalesDiagnosisScenario:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        generator: Generator | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or Generator(provider="deepseek")
        self.registry = registry or ToolRegistry(retriever=self.retriever)

    async def diagnose(self, sku: str, days: int = 14) -> dict[str, Any]:
        diagnosis = await self.registry.diagnose_sales_anomaly(sku, days=days)

        causes = [c["cause"] for c in diagnosis.get("suspected_causes", [])]
        queries = [_CAUSE_KB_QUERIES.get(c, "Amazon operations best practices") for c in causes]
        if not queries:  # healthy SKU: still pull general account-health guidance
            queries = ["account health seller metrics performance"]
        knowledge: list[dict[str, Any]] = []
        for query in queries[:3]:
            knowledge.extend(await self.retriever.retrieve_texts(query, final_top_k=3))

        narration = await self.generator.narrate_sales_diagnosis(sku, diagnosis, knowledge)

        final_answer = self._format_final_answer(sku, diagnosis, narration.get("narrative", ""))
        return {
            "sku": sku,
            "final_answer": final_answer,
            "diagnosis": diagnosis,
            "tool_calls": [
                {
                    "id": "diagnose_sales_anomaly",
                    "type": "function",
                    "function": {
                        "name": "diagnose_sales_anomaly",
                        "arguments": json.dumps({"sku": sku, "days": days}),
                    },
                },
            ],
            "iterations": 1,
            "provider": self.generator.provider,
            "model": self.generator.model,
            "usage": narration.get("usage"),
        }

    @staticmethod
    def _format_final_answer(sku: str, diagnosis: dict[str, Any], narrative: str) -> str:
        changes = diagnosis["metrics"]["change_pct"]
        cur = diagnosis["metrics"]["current"]
        lines = [
            f"# 销量异动诊断 — {sku}（近 {diagnosis['window_days']} 天 vs 前一窗口）",
            "",
            narrative.strip(),
            "",
            "## 指标对比（确定性计算）",
            "",
            "| 指标 | 当前窗口 | 上一窗口 | 变化 |",
            "|---|---|---|---|",
        ]
        rows = [
            ("销量", "units", f"{changes['units']:+.1f}%"),
            ("流量 sessions", "sessions", f"{changes['sessions']:+.1f}%"),
            ("转化率 CVR", "cvr", f"{changes['cvr']:+.1f}%"),
            ("均价", "price", f"{changes['price']:+.1f}%"),
            ("广告花费", "ad_spend", f"{changes['ad_spend']:+.1f}%"),
        ]
        for label, key, change in rows:
            cur_v = cur.get(key)
            lines.append(f"| {label} | {cur_v if cur_v is not None else '—'} | — | {change} |")
        lines.append(
            f"| 平均评分 | {cur.get('avg_rating')} | — | {changes['rating_change']:+.2f} |"
        )

        if diagnosis.get("suspected_causes"):
            lines += ["", "## 疑似原因（代码归因）", ""]
            for cause in diagnosis["suspected_causes"]:
                lines.append(
                    f"- **{_CAUSE_LABELS.get(cause['cause'], cause['cause'])}**"
                    f"（置信度 {cause['confidence']}）：{cause['evidence']}"
                )
        return "\n".join(lines)


_CAUSE_LABELS = {
    "ad_budget_cut": "广告预算削减",
    "organic_traffic_drop": "自然流量下滑",
    "rating_decline": "评分下滑拖累转化",
    "conversion_drop": "转化率下降",
    "price_change": "调价影响",
}
