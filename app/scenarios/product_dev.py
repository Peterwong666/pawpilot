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
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or Generator(provider="deepseek")
        self.registry = registry or ToolRegistry(retriever=self.retriever)

    async def analyze(self, product_type: str) -> dict[str, Any]:
        voc = await self.registry.mine_competitor_reviews(product_type)

        spec_chunks = await self.retriever.retrieve_texts(
            f"PawPilot {product_type} product line specifications materials certifications",
            final_top_k=4,
        )
        compliance_chunks = await self.retriever.retrieve_texts(
            "pet supplies compliance prohibited claims material safety requirements",
            final_top_k=3,
        )
        knowledge = spec_chunks + compliance_chunks

        rep_sku = _REPRESENTATIVE_SKUS.get(product_type)
        profit = await self.registry.analyze_profit(rep_sku) if rep_sku else None
        product_context = "\n\n".join(
            f"[source: {c.get('doc_id')}, {c.get('section')}]\n{c.get('text', '')}"
            for c in spec_chunks
        )

        synthesis = await self.generator.synthesize_product_dev(
            product_type, voc, product_context, knowledge
        )

        final_answer = self._format_final_answer(
            product_type, voc, profit, synthesis.get("report", "")
        )
        return {
            "product_type": product_type,
            "final_answer": final_answer,
            "voc": voc,
            "profit": profit,
            "tool_calls": [
                {
                    "id": "mine_competitor_reviews",
                    "type": "function",
                    "function": {
                        "name": "mine_competitor_reviews",
                        "arguments": json.dumps({"product_type": product_type}),
                    },
                },
            ],
            "iterations": 1,
            "provider": self.generator.provider,
            "model": self.generator.model,
            "usage": synthesis.get("usage"),
        }

    @staticmethod
    def _format_final_answer(
        product_type: str,
        voc: dict[str, Any],
        profit: dict[str, Any] | None,
        report: str,
    ) -> str:
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
