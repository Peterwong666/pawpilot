"""Scenario 2: Listing generation + compliance check.

Fixed two-step pipeline:
1. Retrieve relevant Amazon listing/compliance rules.
2. Generate an English listing via LLM.
3. Run a compliance check on the draft via LLM.

This avoids the open-ended agent loop so latency is predictable and fits the
Streamlit UI's real-time connection budget.
"""

from __future__ import annotations

import json
from typing import Any

from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever


class ListingGenScenario:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        generator: Generator | None = None,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or Generator(provider="deepseek")

    async def generate(self, product_info: dict[str, Any]) -> dict[str, Any]:
        # Build a query that surfaces listing style and prohibited-claim rules.
        query = (
            "Amazon Pet Supplies listing style guide title bullet description rules "
            "prohibited words unsupported claims compliance"
        )
        rules = await self.retriever.retrieve_texts(query)

        draft_result = await self.generator.generate_listing(product_info, rules)
        listing = draft_result["listing"]
        draft_text = self._listing_to_text(listing)

        compliance_result = await self.generator.check_compliance(draft_text, rules)

        final_answer = self._format_final_answer(
            listing, compliance_result.get("compliance", {})
        )
        return {
            "final_answer": final_answer,
            "tool_calls": [
                {
                    "id": "generate_listing",
                    "type": "function",
                    "function": {
                        "name": "generate_listing",
                        "arguments": json.dumps(product_info),
                    },
                },
                {
                    "id": "check_listing_compliance",
                    "type": "function",
                    "function": {
                        "name": "check_listing_compliance",
                        "arguments": json.dumps({"draft_text": draft_text}),
                    },
                },
            ],
            "iterations": 2,
            "provider": self.generator.provider,
            "model": self.generator.model,
            "usage": compliance_result.get("usage", draft_result.get("usage")),
        }

    @staticmethod
    def _listing_to_text(listing: Any) -> str:
        if isinstance(listing, dict):
            return json.dumps(listing, ensure_ascii=False, indent=2)
        return str(listing)

    @staticmethod
    def _format_final_answer(listing: Any, compliance: Any) -> str:
        issues: list[Any] = []
        if isinstance(compliance, dict):
            raw_issues = compliance.get("issues") or compliance.get("violations") or []
            issues = raw_issues if isinstance(raw_issues, list) else []
        passed = isinstance(compliance, dict) and compliance.get("passed", True)
        return (
            "## Generated Listing\n\n"
            f"```json\n{json.dumps(listing, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## Compliance Review\n\n"
            f"Passed: {passed}\n\n"
            f"Issues ({len(issues)}):\n\n"
            + "\n".join(
                f"- [{i.get('severity', 'medium')}] {i.get('field', 'listing')}: "
                f"{i.get('reason', i.get('word_or_phrase', ''))}"
                for i in issues
            )
        )
