"""Scenario 2: Listing generation + hybrid compliance check.

Fixed three-step pipeline:
1. Retrieve relevant Amazon listing/compliance rules.
2. Generate an English listing via LLM.
3. Run a hybrid compliance check:
   a. Deterministic rule engine (instant, free, auditable — see compliance_engine.py).
   b. LLM semantic check for unsupported claims the rules cannot express.

This avoids the open-ended agent loop so latency is predictable and fits the
Streamlit UI's real-time connection budget.
"""

from __future__ import annotations

import json
from typing import Any

from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever
from app.scenarios.compliance_engine import ComplianceRuleEngine


class ListingGenScenario:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        generator: Generator | None = None,
        rule_engine: ComplianceRuleEngine | None = None,
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or Generator(provider="deepseek")
        self.rule_engine = rule_engine or ComplianceRuleEngine()

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

        # Hybrid check: deterministic rules first (free, instant), then LLM semantics.
        rule_issues = self.rule_engine.check_draft(draft_text)
        compliance_result = await self.generator.check_compliance(draft_text, rules)
        llm_compliance = compliance_result.get("compliance", {})

        final_answer = self._format_final_answer(listing, rule_issues, llm_compliance)
        return {
            "final_answer": final_answer,
            "rule_issues": rule_issues,
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
    def _llm_issues(compliance: Any) -> list[dict[str, Any]]:
        """Normalize LLM compliance output into a flat issue list."""
        if not isinstance(compliance, dict):
            return []
        raw = compliance.get("issues") or compliance.get("violations") or []
        if not isinstance(raw, list):
            return []
        normalized = []
        for issue in raw:
            if not isinstance(issue, dict):
                continue
            normalized.append({
                "severity": issue.get("severity", "medium"),
                "field": issue.get("field", "listing"),
                "match": issue.get("word_or_phrase", ""),
                "reason": issue.get("reason", ""),
                "suggested_rewrite": issue.get("suggested_rewrite", ""),
                "source": "llm",
            })
        return normalized

    @classmethod
    def _format_final_answer(
        cls,
        listing: Any,
        rule_issues: list[dict[str, Any]],
        llm_compliance: Any,
    ) -> str:
        llm_issues = cls._llm_issues(llm_compliance)
        critical_count = sum(
            1 for i in rule_issues if i.get("severity") == "critical"
        ) + sum(1 for i in llm_issues if str(i.get("severity")).lower() in ("critical", "high"))
        passed = critical_count == 0

        lines = [
            "## Generated Listing",
            "",
            f"```json\n{json.dumps(listing, ensure_ascii=False, indent=2)}\n```",
            "",
            "## Compliance Review (hybrid: rule engine + LLM)",
            "",
            f"Passed: {passed} (critical issues: {critical_count})",
            "",
            f"Rule-engine issues ({len(rule_issues)}):",
            "",
        ]
        lines += [
            f"- [{i.get('severity')}] [{i.get('rule_id')}] {i.get('field')}: "
            f"\"{i.get('match')}\" — {i.get('message')} Fix: {i.get('fix_hint')}"
            for i in rule_issues
        ]
        lines += ["", f"LLM semantic issues ({len(llm_issues)}):", ""]
        lines += [
            f"- [{i.get('severity')}] {i.get('field')}: {i.get('reason')} "
            f"Rewrite: {i.get('suggested_rewrite')}"
            for i in llm_issues
        ]
        return "\n".join(lines)
