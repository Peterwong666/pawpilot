"""End-to-end ingestion pipeline.

1. Parse Markdown documents.
2. Chunk them using the configured strategy.
3. Compute embeddings.
4. Insert into Postgres.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.rag.ingestion.chunking import Chunk, get_chunker
from app.rag.ingestion.embeddings import EmbeddingClient
from app.rag.ingestion.parser import parse_directory
from app.rag.ingestion.store import ChunkStore


class IngestionPipeline:
    """Orchestrate parsing, chunking, embedding, and storage."""

    def __init__(
        self,
        strategy: str = "hierarchical",
        store: ChunkStore | None = None,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self.strategy = strategy
        self.chunker = get_chunker(strategy)
        self.store = store or ChunkStore()
        self.embedder = embedder or EmbeddingClient()

    async def ingest_directory(
        self,
        root: Path,
        glob: str = "**/*.md",
        batch_size: int = 32,
    ) -> dict[str, int]:
        """Ingest all Markdown files under root. Returns stats."""
        documents = parse_directory(root, glob)
        all_chunks: list[Chunk] = []
        for doc in documents:
            all_chunks.extend(self.chunker.split(doc.text, doc.id, doc.title))

        # Embed in batches and prepare for storage.
        prepared: list[dict[str, Any]] = []
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            embeddings = await self.embedder.embed([c.text for c in batch])
            for chunk, emb in zip(batch, embeddings, strict=False):
                prepared.append(
                    {
                        "doc_id": chunk.doc_id,
                        "title": chunk.title,
                        "section": chunk.section,
                        "text": chunk.text,
                        "strategy": chunk.strategy,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "embedding": emb,
                        "metadata": {"strategy": chunk.strategy},
                    }
                )

        self.store.insert_chunks(prepared)
        return {
            "documents": len(documents),
            "chunks": len(all_chunks),
            "stored": len(prepared),
        }


async def run_ingestion(
    root: Path,
    strategy: str = "hierarchical",
    reset: bool = False,
) -> dict[str, int]:
    """Convenience entry point."""
    pipeline = IngestionPipeline(strategy=strategy)
    pipeline.store.init_schema()
    if reset:
        pipeline.store.reset()
    return await pipeline.ingest_directory(root)
