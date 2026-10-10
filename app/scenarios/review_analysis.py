"""Scenario 3: Review analysis and action recommendations.

Uses the agent loop to query review data and then synthesize insights with SOP guidance.
"""

from __future__ import annotations

from app.agent.runtime import AgentRuntime


class ReviewAnalysisScenario:
    def __init__(
        self,
        runtime: AgentRuntime | None = None,
        provider: str = "deepseek",
        account_id: str = "default",
        marketplace: str = "US",
        use_simulated: bool = True,
    ) -> None:
        self.runtime = runtime or AgentRuntime(
            provider=provider,
            account_id=account_id,
            marketplace=marketplace,
            use_simulated=use_simulated,
            system_prompt=(
                "You are a customer-insights analyst for PawPilot, an Amazon US pet-supplies "
                "brand. When given a SKU, use the analyze_reviews tool to get theme "
                "distribution and rating trend, and use search_policies to look up the "
                "negative-review response SOP and review policy when needed. 用中文输出分析报告，"
                "要求：1) 每条行动建议注明依据，能引用 SOP 的标注 [source: doc_id, section]，否则标注 [建议]；"
                "2) 对差评判断是否符合亚马逊移除政策，说明「可申请移除/不可移除/需人工判断」；"
                "3) 回复差评时给出 SOP 模板编号；4) 只使用工具返回的数据，禁止编造。"
            ),
        )

    async def analyze(self, sku: str | list[str], days: int = 90) -> dict[str, object]:
        skus = [sku] if isinstance(sku, str) else list(sku)
        if not skus:
            return {"sku": "", "final_answer": "未选择 SKU。", "tool_calls": [], "iterations": 0}

        if len(skus) == 1:
            prompt = f"Analyze reviews for SKU {skus[0]} over the last {days} days and recommend actions."
        else:
            sku_list = ", ".join(skus)
            prompt = (
                f"Analyze reviews for SKUs {sku_list} over the last {days} days and recommend actions. "
                f"Compare the themes across these SKUs and highlight common pain points."
            )
        result = await self.runtime.run(prompt)
        return {
            "sku": ",".join(skus),
            "skus": skus,
            "final_answer": result.final_answer,
            "tool_calls": result.tool_calls,
            "iterations": result.iterations,
            "provider": result.provider,
            "model": result.model,
        }
