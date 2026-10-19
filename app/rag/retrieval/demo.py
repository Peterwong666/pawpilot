"""Offline retrieval for demo mode: DuckDB in-memory store + local hash embeddings.

Mirrors the HybridRetriever pipeline shape (dense + keyword retrieval fused with
RRF) without PostgreSQL, pgvector or any embedding/rerank API, so
``PAWPILOT_DEMO_MODE=1`` can serve a full Q&A loop from the tiny bundled corpus
under ``demo/knowledge_base/``.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import duckdb
import jieba

from app.core.mock_llm import LocalHashEmbedder
from app.rag.ingestion.chunking import HierarchicalChunker
from app.rag.ingestion.embeddings import cosine_similarity
from app.rag.ingestion.parser import parse_directory

logger = logging.getLogger(__name__)

# demo/knowledge_base lives at the repo root: app/rag/retrieval/demo.py -> parents[3].
DEMO_CORPUS_ROOT = Path(__file__).resolve().parents[3] / "demo" / "knowledge_base"

_RRF_K = 60
_DEFAULT_FINAL_TOP_K = 6


class DemoChunkStore:
    """In-memory DuckDB table of embedded demo chunks (process-wide singleton)."""

    _instance: DemoChunkStore | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.con = duckdb.connect(":memory:")
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS demo_chunks ("
            "id INTEGER PRIMARY KEY, doc_id VARCHAR, title VARCHAR, "
            "section VARCHAR, text VARCHAR, embedding DOUBLE[])"
        )

    @classmethod
    def instance(cls) -> DemoChunkStore:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def count_chunks(self) -> int:
        row = self.con.execute("SELECT count(*) FROM demo_chunks").fetchone()
        return int(row[0]) if row else 0

    def insert_chunks(self, rows: list[tuple[int, str, str, str, str, list[float]]]) -> None:
        self.con.executemany(
            "INSERT INTO demo_chunks (id, doc_id, title, section, text, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )

    def all_chunks(self) -> list[dict[str, Any]]:
        result = self.con.execute(
            "SELECT id, doc_id, title, section, text, embedding FROM demo_chunks ORDER BY id"
        ).fetchall()
        return [
            {
                "id": row[0],
                "doc_id": row[1],
                "title": row[2],
                "section": row[3],
                "text": row[4],
                "embedding": [float(v) for v in row[5]],
            }
            for row in result
        ]


class DemoRetriever:
    """Hybrid-style retrieval over the bundled demo corpus (no network, no Postgres)."""

    def __init__(
        self,
        store: DemoChunkStore | None = None,
        embedder: LocalHashEmbedder | None = None,
        corpus_root: Path | None = None,
    ) -> None:
        self.store = store or DemoChunkStore.instance()
        self.embedder = embedder or LocalHashEmbedder()
        self.corpus_root = corpus_root or DEMO_CORPUS_ROOT

    async def ensure_ingested(self) -> int:
        """Ingest the bundled demo corpus once (idempotent). Returns the chunk count."""
        existing = self.store.count_chunks()
        if existing > 0:
            return existing
        docs = parse_directory(self.corpus_root)
        chunker = HierarchicalChunker(size=384, overlap=48)
        chunks = [c for doc in docs for c in chunker.split(doc.text, doc.id, doc.title)]
        embeddings = await self.embedder.embed([c.text for c in chunks])
        rows = [
            (idx + 1, chunk.doc_id, chunk.title, chunk.section, chunk.text, embedding)
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        self.store.insert_chunks(rows)
        count = self.store.count_chunks()
        logger.info("Demo corpus ingested: %d chunks from %s", count, self.corpus_root)
        return count

    async def retrieve_texts(
        self,
        query: str,
        retrieval_top_k: int | None = None,
        final_top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Dense (cosine) + keyword (token overlap) retrieval fused with RRF."""
        await self.ensure_ingested()
        final_k = final_top_k or _DEFAULT_FINAL_TOP_K
        chunks = self.store.all_chunks()
        if not chunks:
            return []

        # Dense ranking by cosine similarity against the local hash embedding.
        query_emb = await self.embedder.embed_query(query)
        dense_scored = sorted(
            ((cosine_similarity(query_emb, c["embedding"]), c["id"]) for c in chunks),
            key=lambda item: item[0],
            reverse=True,
        )
        dense_rank = {cid: rank for rank, (_, cid) in enumerate(dense_scored, start=1)}

        # Keyword ranking by jieba token overlap count.
        query_tokens = [t.strip().lower() for t in jieba.lcut(query) if t.strip()]
        keyword_scored = []
        for chunk in chunks:
            text_lower = chunk["text"].lower()
            overlap = sum(text_lower.count(tok) for tok in set(query_tokens))
            keyword_scored.append((overlap, chunk["id"]))
        keyword_scored.sort(key=lambda item: item[0], reverse=True)
        keyword_rank = {cid: rank for rank, (_, cid) in enumerate(keyword_scored, start=1)}

        # RRF fusion (same formula as HybridRetriever).
        scores: dict[int, float] = {}
        for chunk in chunks:
            cid = chunk["id"]
            score = 1.0 / (_RRF_K + dense_rank[cid]) + 1.0 / (_RRF_K + keyword_rank[cid])
            scores[cid] = score

        by_id = {c["id"]: c for c in chunks}
        fused_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        top_ids = [cid for cid in fused_ids[:final_k] if scores[cid] > 0]
        return [
            {
                "id": by_id[cid]["id"],
                "doc_id": by_id[cid]["doc_id"],
                "title": by_id[cid]["title"],
                "section": by_id[cid]["section"],
                "text": by_id[cid]["text"],
                "rrf_score": scores[cid],
                "rerank_score": None,
            }
            for cid in top_ids
        ]
