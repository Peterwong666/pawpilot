"""Hybrid retrieval: vector + keyword fusion + rerank.

The pipeline follows the standard recipe:
1. Dense retrieval from pgvector.
2. Keyword retrieval from Postgres full-text search.
3. Reciprocal Rank Fusion (RRF) to combine both result lists.
4. Cross-encoder reranker to produce the final ordered list.

All hyperparameters are read from Settings so experiments are reproducible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.rag.ingestion.embeddings import EmbeddingClient, RerankClient
from app.rag.ingestion.store import ChunkStore, StoredChunk

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk: StoredChunk
    vector_rank: int | None
    keyword_rank: int | None
    rrf_score: float
    rerank_score: float | None


class HybridRetriever:
    def __init__(
        self,
        store: ChunkStore | None = None,
        embedder: EmbeddingClient | None = None,
        reranker: RerankClient | None = None,
    ) -> None:
        self.settings = get_settings()
        self.store = store or ChunkStore()
        self.embedder = embedder or EmbeddingClient()
        self.reranker = reranker or RerankClient()

    async def retrieve(
        self,
        query: str,
        retrieval_top_k: int | None = None,
        final_top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Run hybrid retrieval with RRF and reranking."""
        top_k = retrieval_top_k or self.settings.retrieval_top_k
        final_k = final_top_k or self.settings.final_top_k
        rrf_const = self.settings.rrf_k

        # Dense + keyword retrieval in parallel. Each half degrades independently so
        # that a broken index downgrades result quality rather than failing the request.
        query_emb = await self.embedder.embed_query(query)
        try:
            vector_results = self.store.vector_search(query_emb, top_k=top_k)
        except Exception:
            logger.warning("Vector search failed; degrading to keyword-only retrieval")
            vector_results = []
        try:
            keyword_results = self.store.keyword_search(query, top_k=top_k)
        except Exception:
            logger.warning("Keyword search failed; degrading to dense-only retrieval")
            keyword_results = []

        # RRF fusion.
        scores: dict[int, float] = {}
        ranks: dict[int, dict[str, int]] = {}
        for rank, chunk in enumerate(vector_results, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (rrf_const + rank)
            ranks.setdefault(chunk.id, {})["vector"] = rank
        for rank, chunk in enumerate(keyword_results, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (rrf_const + rank)
            ranks.setdefault(chunk.id, {})["keyword"] = rank

        # Deduplicate and order by RRF score.
        unique_chunks = {chunk.id: chunk for chunk in (vector_results + keyword_results)}
        fused_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
        fused = [unique_chunks[cid] for cid in fused_ids]

        # Rerank top candidates.
        rerank_candidates = fused[: max(final_k, 20)]
        rerank_scores: dict[int, float] = {}
        if rerank_candidates:
            try:
                rerank_out = await self.reranker.rerank(
                    query=query,
                    documents=[c.text for c in rerank_candidates],
                    top_n=len(rerank_candidates),
                )
                for idx, score in rerank_out:
                    rerank_scores[rerank_candidates[idx].id] = score
            except Exception:
                # If rerank endpoint is unavailable, fall back to RRF order.
                rerank_scores = {c.id: scores[c.id] for c in rerank_candidates}

        # Build final result ordered by rerank score, fallback to RRF score.
        result = [
            RetrievedChunk(
                chunk=chunk,
                vector_rank=ranks.get(chunk.id, {}).get("vector"),
                keyword_rank=ranks.get(chunk.id, {}).get("keyword"),
                rrf_score=scores[chunk.id],
                rerank_score=rerank_scores.get(chunk.id),
            )
            for chunk in rerank_candidates
        ]
        result.sort(
            key=lambda rc: (rc.rerank_score if rc.rerank_score is not None else rc.rrf_score),
            reverse=True,
        )
        return result[:final_k]

    async def retrieve_texts(
        self,
        query: str,
        retrieval_top_k: int | None = None,
        final_top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Convenience method returning plain dictionaries for downstream use."""
        chunks = await self.retrieve(query, retrieval_top_k, final_top_k)
        return [
            {
                "id": rc.chunk.id,
                "doc_id": rc.chunk.doc_id,
                "title": rc.chunk.title,
                "section": rc.chunk.section,
                "text": rc.chunk.text,
                "rrf_score": rc.rrf_score,
                "rerank_score": rc.rerank_score,
            }
            for rc in chunks
        ]
