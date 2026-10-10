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
from app.data.hybrid_store import HybridDataStore
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

    async def diagnose(self, sku: str | list[str], days: int = 14) -> dict[str, Any]:
        skus = [sku] if isinstance(sku, str) else list(sku)
        if not skus:
            return {"sku": "", "final_answer": "未选择 SKU。", "diagnoses": [], "tool_calls": [], "iterations": 0}

        # Run deterministic diagnosis for each SKU (code, not LLM).
        diagnoses: list[dict[str, Any]] = []
        for s in skus:
            diagnoses.append(await self.registry.diagnose_sales_anomaly(s, days=days))

        # Collect all suspected causes across SKUs for KB retrieval.
        all_causes = {
            c["cause"] for d in diagnoses for c in d.get("suspected_causes", [])
        }
        queries = [_CAUSE_KB_QUERIES.get(c, "Amazon operations best practices") for c in all_causes]
        if not queries:
            queries = ["account health seller metrics performance"]
        knowledge: list[dict[str, Any]] = []
        for query in queries[:3]:
            knowledge.extend(await self.retriever.retrieve_texts(query, final_top_k=3))

        # LLM narrates only once for the whole batch to keep context bounded.
        narration = await self.generator.narrate_sales_diagnosis(
            skus[0] if len(skus) == 1 else ",".join(skus),
            diagnoses[0] if len(skus) == 1 else {"sku_list": skus, "diagnoses": diagnoses},
            knowledge,
        )

        final_answer = self._format_final_answer(skus, diagnoses, narration.get("narrative", ""))
        return {
            "sku": ",".join(skus),
            "skus": skus,
            "final_answer": final_answer,
            "diagnoses": diagnoses,
            "diagnosis": diagnoses[0] if len(diagnoses) == 1 else None,
            "tool_calls": [
                {
                    "id": "diagnose_sales_anomaly",
                    "type": "function",
                    "function": {
                        "name": "diagnose_sales_anomaly",
                        "arguments": json.dumps({"sku": s, "days": days}),
                    },
                }
                for s in skus
            ],
            "iterations": 1,
            "provider": self.generator.provider,
            "model": self.generator.model,
            "usage": narration.get("usage"),
        }

    @staticmethod
    def _format_final_answer(skus: list[str], diagnoses: list[dict[str, Any]], narrative: str) -> str:
        if len(skus) == 1:
            sku = skus[0]
            diagnosis = diagnoses[0]
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

        # Multi-SKU summary.
        lines = [
            f"# 销量异动诊断 — {len(skus)} 个 SKU（近 {diagnoses[0]['window_days']} 天 vs 前一窗口）",
            "",
            narrative.strip(),
            "",
            "## 汇总指标对比（确定性计算）",
            "",
            "| SKU | 销量变化 | 流量变化 | CVR变化 | 均价变化 | 广告花费变化 | 评分变化 | 状态 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for sku, diagnosis in zip(skus, diagnoses, strict=True):
            changes = diagnosis["metrics"]["change_pct"]
            lines.append(
                f"| {sku} | {changes['units']:+.1f}% | {changes['sessions']:+.1f}% | "
                f"{changes['cvr']:+.1f}% | {changes['price']:+.1f}% | "
                f"{changes['ad_spend']:+.1f}% | {changes['rating_change']:+.2f} | "
                f"{diagnosis.get('status', 'normal')} |"
            )
        # Per-SKU suspected causes.
        anomaly_skus = [(s, d) for s, d in zip(skus, diagnoses, strict=True) if d.get("status") == "anomaly_detected"]
        if anomaly_skus:
            lines += ["", "## 异动 SKU 疑似原因（代码归因）", ""]
            for sku, diagnosis in anomaly_skus:
                lines.append(f"### {sku}")
                for cause in diagnosis.get("suspected_causes", []):
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
