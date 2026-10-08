"""Embedding and reranking helpers.

We use OpenAI-compatible embedding/rerank endpoints (SiliconFlow by default) so the code stays
vendor-neutral and easy to switch.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.llm import current_loop_id

# One shared client per (event loop, endpoint kind) so that embedding/rerank calls
# reuse keep-alive connections instead of rebuilding an httpx pool every request.
_clients: dict[tuple[int, str], AsyncOpenAI] = {}

# Identical queries are common (demos, evaluation runs), and embeddings are
# deterministic for a fixed model, so a small bounded cache is always safe.
_query_cache: dict[tuple[str, str], list[float]] = {}
_QUERY_CACHE_MAX = 512


def _shared_client(kind: str, timeout: float, max_retries: int) -> AsyncOpenAI:
    key = (current_loop_id(), kind)
    client = _clients.get(key)
    if client is None:
        settings = get_settings()
        client = AsyncOpenAI(
            base_url=settings.siliconflow_base_url,
            api_key=settings.siliconflow_api_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        _clients[key] = client
    return client


def clear_embedding_cache() -> None:
    """Drop cached query embeddings (used by tests and long-running workers)."""
    _query_cache.clear()


class EmbeddingClient:
    """Thin wrapper around an OpenAI-compatible embedding endpoint."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = _shared_client(
            "embedding", settings.embed_timeout, settings.embed_max_retries
        )
        self.model = settings.embedding_model
        self.dim = settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a list of texts."""
        if not texts:
            return []
        # Sanitize empty strings to avoid API rejection.
        safe_texts = [t if t.strip() else " " for t in texts]
        response = await self.client.embeddings.create(
            input=safe_texts,
            model=self.model,
            encoding_format="float",
        )
        return [item.embedding for item in response.data]

    async def embed_query(self, text: str) -> list[float]:
        """Return the embedding for a single query, served from cache when possible."""
        cache_key = (self.model, text)
        cached = _query_cache.get(cache_key)
        if cached is not None:
            return cached
        result = (await self.embed([text]))[0]
        if len(_query_cache) >= _QUERY_CACHE_MAX:
            _query_cache.clear()
        _query_cache[cache_key] = result
        return result


class RerankClient:
    """Thin wrapper around an OpenAI-compatible rerank endpoint."""

    def __init__(self) -> None:
        settings = get_settings()
        self.client = _shared_client(
            "rerank", settings.embed_timeout, settings.embed_max_retries
        )
        self.model = settings.rerank_model

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[tuple[int, float]]:
        """Return (doc_index, score) pairs sorted by relevance descending."""
        if not documents:
            return []
        top_n = top_n or len(documents)
        # SiliconFlow rerank API accepts `query` and `documents` and returns `results`.
        response = await self.client.post(
            "/rerank",
            cast_to=dict[str, Any],
            body={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": min(top_n, len(documents)),
            },
        )
        results = response.get("results", [])
        return [(int(r["index"]), float(r["relevance_score"])) for r in results]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _main() -> None:
    """Quick sanity check (requires SILICONFLOW_API_KEY)."""
    ec = EmbeddingClient()
    out = await ec.embed(["test", "another"])
    print(len(out), len(out[0]))


if __name__ == "__main__":
    asyncio.run(_main())
