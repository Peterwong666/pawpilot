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
    ) -> None:
        self.retriever = retriever or HybridRetriever()
        self.generator = generator or Generator(provider="deepseek")

    async def answer(self, query: str) -> dict[str, Any]:
        chunks = await self.retriever.retrieve_texts(query)
        result = await self.generator.answer_policy_question(query, chunks)
        return result
