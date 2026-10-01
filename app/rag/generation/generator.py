"""Generation layer: assemble prompts, call LLM, parse structured output.

Supports both DeepSeek and Qwen providers. Tracks token usage and latency for cost reporting.
"""

from __future__ import annotations

import json
import time
from typing import Any

from openai import AsyncOpenAI

from app.core.llm import get_async_client, resolve_model
from app.rag.generation.prompts import (
    compliance_check_prompt,
    listing_generation_prompt,
    policy_qa_prompt,
    review_analysis_prompt,
)


class GenerationUsage:
    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.latency_seconds = 0.0


class Generator:
    """Provider-agnostic async generator."""

    def __init__(self, provider: str = "deepseek") -> None:
        self.provider = provider
        self.client: AsyncOpenAI = get_async_client(provider)
        self.model = resolve_model(provider)
        self.usage = GenerationUsage()

    async def _chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.3,
        response_format: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        start = time.perf_counter()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format
        completion = await self.client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - start
        content = completion.choices[0].message.content or ""
        self.usage.calls += 1
        self.usage.input_tokens += completion.usage.prompt_tokens if completion.usage else 0
        self.usage.output_tokens += completion.usage.completion_tokens if completion.usage else 0
        self.usage.latency_seconds += latency
        return content, {"provider": self.provider, "model": self.model, "latency": latency}

    async def answer_policy_question(
        self,
        query: str,
        context_chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system, user = policy_qa_prompt(query, context_chunks)
        answer, meta = await self._chat(system, user, temperature=0.2)
        return {
            "answer": answer,
            "sources": [
                {"doc_id": c.get("doc_id"), "section": c.get("section"), "text": c.get("text")}
                for c in context_chunks
            ],
            "meta": meta,
            "usage": self._snapshot(),
        }

    async def generate_listing(
        self,
        product_info: dict[str, Any],
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system, user = listing_generation_prompt(product_info, rules)
        content, meta = await self._chat(
            system,
            user,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        parsed = self._safe_json_parse(content)
        return {"listing": parsed, "meta": meta, "usage": self._snapshot()}

    async def check_compliance(
        self,
        draft_text: str,
        rules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system, user = compliance_check_prompt(draft_text, rules)
        content, meta = await self._chat(
            system,
            user,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        parsed = self._safe_json_parse(content)
        return {"compliance": parsed, "meta": meta, "usage": self._snapshot()}

    async def analyze_reviews(
        self,
        asin: str,
        reviews_summary: str,
        knowledge_chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system, user = review_analysis_prompt(asin, reviews_summary, knowledge_chunks)
        content, meta = await self._chat(
            system,
            user,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        parsed = self._safe_json_parse(content)
        return {"analysis": parsed, "meta": meta, "usage": self._snapshot()}

    def _snapshot(self) -> dict[str, Any]:
        return {
            "calls": self.usage.calls,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "latency_seconds": round(self.usage.latency_seconds, 3),
        }

    @staticmethod
    def _safe_json_parse(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Best-effort: strip markdown fences.
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return {"raw": text, "parse_error": True}
