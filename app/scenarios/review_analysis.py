"""Scenario 3: Review analysis and action recommendations.

Uses the agent loop to query review data and then synthesize insights with SOP guidance.
"""

from __future__ import annotations

from app.agent.runtime import AgentRuntime


class ReviewAnalysisScenario:
    def __init__(self, runtime: AgentRuntime | None = None) -> None:
        self.runtime = runtime or AgentRuntime(
            provider="deepseek",
            system_prompt=(
                "You are a customer-insights analyst for PawPilot. When given a SKU, use the "
                "analyze_reviews tool to summarize themes and recommended actions. Present the "
                "results concisely with clear next steps."
            ),
        )

    async def analyze(self, sku: str, days: int = 90) -> dict[str, object]:
        prompt = f"Analyze reviews for SKU {sku} over the last {days} days and recommend actions."
        result = await self.runtime.run(prompt)
        return {
            "sku": sku,
            "final_answer": result.final_answer,
            "tool_calls": result.tool_calls,
            "iterations": result.iterations,
            "provider": result.provider,
            "model": result.model,
        }
