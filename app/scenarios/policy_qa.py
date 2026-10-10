"""Scenario 1: Policy and compliance Q&A.

Pure RAG answer with citations. No agent loop needed because the task is a single retrieval
+ generation step.
"""

from __future__ import annotations

from typing import Any

from app.rag.generation.generator import Generator
from app.rag.retrieval.hybrid import HybridRetriever


class PolicyQAScenario:
    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        generator: Generator | None = None,
        provider: str = "deepseek",
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or Generator(provider=provider)
        self.provider = provider

    async def answer(self, query: str) -> dict[str, Any]:
        chunks = await self.retriever.retrieve_texts(query)
        result = await self.generator.answer_policy_question(query, chunks)
        # Surface model/provider at top level for consistency with other scenarios.
        meta = result.get("meta", {})
        result.setdefault("provider", meta.get("provider", self.provider))
        result.setdefault("model", meta.get("model"))
        return result
