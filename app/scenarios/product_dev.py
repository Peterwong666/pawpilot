"""Scenario 6: Competitor VOC → product development opportunities (产品开发).

Serves the product-development role: before iterating a product line, mine what
competitor customers complain about, map unmet needs to our specs, and check the
unit economics so improvement decisions are made against margin reality.

Fixed pipeline, deterministic core:
1. ``mine_competitor_reviews`` aggregates competitor VOC by theme (code, not LLM).
2. Our own product-line specs and compliance rules are retrieved from the KB.
3. ``analyze_profit`` supplies pricing/margin context for the representative SKU.
4. The LLM synthesizes a Chinese improvement-opportunity report; quotes and counts
   come from the deterministic VOC layer.
"""

from __future__ import annotations

import json
from typing import Any

from app.agent.tools import ToolRegistry
from app.data.hybrid_store import HybridDataStore
from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever

# Product line → representative own SKU used for the pricing/margin context.
_REPRESENTATIVE_SKUS: dict[str, str] = {
    "rope toy": "PP-RT-102",
    "harness": "PP-HR-203",
    "feeder bowl": "PP-SB-302",
}


class ProductDevScenario:
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

    async def analyze(self, product_type: str | list[str]) -> dict[str, Any]:
        product_types = [product_type] if isinstance(product_type, str) else list(product_type)
        if not product_types:
            return {"product_type": "", "final_answer": "未选择产品类型。", "vocs": [], "tool_calls": [], "iterations": 0}

        # Run deterministic VOC for each product type (code, not LLM).
        vocs: list[dict[str, Any]] = []
        profits: list[dict[str, Any] | None] = []
        for pt in product_types:
            voc = await self.registry.mine_competitor_reviews(pt)
            vocs.append(voc)
            rep_sku = _REPRESENTATIVE_SKUS.get(pt)
            profit = await self.registry.analyze_profit(rep_sku) if rep_sku else None
            profits.append(profit)

        # Retrieve specs + compliance once (shared context).
        spec_queries = " ".join(
            f"PawPilot {pt} product line specifications materials certifications" for pt in product_types
        )
        spec_chunks = await self.retriever.retrieve_texts(spec_queries, final_top_k=4)
        compliance_chunks = await self.retriever.retrieve_texts(
            "pet supplies compliance prohibited claims material safety requirements",
            final_top_k=3,
        )
        knowledge = spec_chunks + compliance_chunks
        product_context = "\n\n".join(
            f"[source: {c.get('doc_id')}, {c.get('section')}]\n{c.get('text', '')}"
            for c in spec_chunks
        )

        primary_pt = product_types[0]
        primary_voc = vocs[0]
        primary_profit = profits[0]
        combined_voc = primary_voc
        if len(vocs) > 1:
            combined_voc = {
                "product_type": ", ".join(product_types),
                "competitors": [c for v in vocs for c in v.get("competitors", [])],
                "total_reviews": sum(v.get("total_reviews", 0) for v in vocs),
                "themes": [t for v in vocs for t in v.get("themes", [])],
            }

        synthesis = await self.generator.synthesize_product_dev(
            primary_pt, combined_voc, product_context, knowledge
        )

        final_answer = self._format_final_answer(
            product_types, vocs, profits, synthesis.get("report", "")
        )
        return {
            "product_type": ",".join(product_types),
            "product_types": product_types,
            "final_answer": final_answer,
            "voc": primary_voc,
            "vocs": vocs,
            "profit": primary_profit,
            "tool_calls": [
                {
                    "id": "mine_competitor_reviews",
                    "type": "function",
                    "function": {
                        "name": "mine_competitor_reviews",
                        "arguments": json.dumps({"product_type": pt}),
                    },
                }
                for pt in product_types
            ],
            "iterations": 1,
            "provider": self.generator.provider,
            "model": self.generator.model,
            "usage": synthesis.get("usage"),
        }

    @staticmethod
    def _format_final_answer(
        product_types: list[str],
        vocs: list[dict[str, Any]],
        profits: list[dict[str, Any] | None],
        report: str,
    ) -> str:
        if len(product_types) == 1:
            product_type = product_types[0]
            voc = vocs[0]
            profit = profits[0]
            lines = [
                f"# 产品改进机会报告 — {product_type}（竞品 VOC 挖掘）",
                "",
                report.strip(),
                "",
                "## 竞品未满足需求数据（确定性聚合）",
                "",
                "| 主题 | 提及次数 | 差评占比 | 平均评分 |",
                "|---|---|---|---|",
            ]
            for theme in voc["themes"]:
                if theme["theme"] == "positive":
                    continue
                lines.append(
                    f"| {theme['theme']} | {theme['count']} | {theme['negative_share_pct']}% "
                    f"| {theme['avg_rating']} |"
                )
            competitor = voc["competitors"][0] if voc["competitors"] else {}
            lines += ["", f"数据来源：竞品 {competitor.get('competitor', '—')}（{competitor.get('reviews', 0)} 条评论，"
                      f"平均 {competitor.get('avg_rating', '—')} 分）。"]
            if profit:
                lines += [
                    "",
                    "## 自家产品利润参考（代表 SKU）",
                    "",
                    f"- SKU：{profit['sku']}，现价 ${profit['price']}，单件毛利 "
                    f"${profit['margin_per_unit']}（{profit['margin_pct']}%）",
                    f"- 盈亏平衡价 ${profit['break_even_price']}；改进规格如增加成本，需保持售价 ≥ 该平衡价 + 目标毛利。",
                ]
            return "\n".join(lines)

        # Multi product-type report.
        lines = [
            f"# 产品改进机会报告 — {len(product_types)} 个产品线（竞品 VOC 挖掘）",
            "",
            report.strip(),
            "",
        ]
        for pt, voc, profit in zip(product_types, vocs, profits, strict=True):
            lines += [f"## {pt}", ""]
            lines += ["| 主题 | 提及次数 | 差评占比 | 平均评分 |", "|---|---|---|---|"]
            for theme in voc["themes"]:
                if theme["theme"] == "positive":
                    continue
                lines.append(
                    f"| {theme['theme']} | {theme['count']} | {theme['negative_share_pct']}% "
                    f"| {theme['avg_rating']} |"
                )
            competitor = voc["competitors"][0] if voc["competitors"] else {}
            lines += ["", f"数据来源：竞品 {competitor.get('competitor', '—')}（{competitor.get('reviews', 0)} 条评论，"
                      f"平均 {competitor.get('avg_rating', '—')} 分）。"]
            if profit:
                lines += [
                    f"- 代表 SKU：{profit['sku']}，现价 ${profit['price']}，单件毛利 "
                    f"${profit['margin_per_unit']}（{profit['margin_pct']}%），盈亏平衡价 ${profit['break_even_price']}。",
                ]
            lines.append("")
        return "\n".join(lines)
