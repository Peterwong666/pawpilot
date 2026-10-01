"""Vector and full-text storage layer backed by PostgreSQL + pgvector.

This module owns the schema, indexing, and CRUD operations for chunks. It keeps both vector
search (pgvector) and keyword search (tsvector) in one table to simplify operations and
self-hosting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.core.config import get_settings


@dataclass
class StoredChunk:
    id: int
    doc_id: str
    title: str
    section: str
    text: str
    strategy: str
    start_char: int
    end_char: int
    embedding: list[float] | None
    keywords: list[str] | None


class ChunkStore:
    """Postgres-backed store for text chunks with vector and keyword indexes."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or get_settings().database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn)

    def init_schema(self) -> None:
        """Create extensions, table, and indexes."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
                dim = get_settings().embedding_dim
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS chunks (
                        id BIGSERIAL PRIMARY KEY,
                        doc_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        section TEXT NOT NULL,
                        text TEXT NOT NULL,
                        strategy TEXT NOT NULL,
                        start_char INTEGER NOT NULL,
                        end_char INTEGER NOT NULL,
                        embedding VECTOR({dim}),
                        keywords TSVECTOR,
                        metadata JSONB DEFAULT '{{}}',
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chunks_doc_id
                    ON chunks(doc_id);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chunks_keywords
                    ON chunks USING GIN(keywords);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chunks_embedding
                    ON chunks USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100);
                """)
            conn.commit()

    def reset(self) -> None:
        """Drop all chunks. Useful for re-ingestion."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE chunks RESTART IDENTITY;")
            conn.commit()

    def insert_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> None:
        """Insert a batch of prepared chunks.

        Each chunk dict must contain: doc_id, title, section, text, strategy,
        start_char, end_char, embedding (list[float]), metadata (dict).
        """
        if not chunks:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                for chunk in chunks:
                    text = chunk["text"]
                    metadata = chunk.get("metadata", {})
                    cur.execute(
                        """
                        INSERT INTO chunks
                        (doc_id, title, section, text, strategy, start_char, end_char,
                         embedding, keywords, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, to_tsvector('english', %s), %s::jsonb)
                        """,
                        (
                            chunk["doc_id"],
                            chunk["title"],
                            chunk["section"],
                            text,
                            chunk["strategy"],
                            chunk["start_char"],
                            chunk["end_char"],
                            str(chunk["embedding"]),
                            text,
                            Jsonb(metadata),
                        ),
                    )
            conn.commit()

    def _row_to_chunk(self, row: tuple[Any, ...]) -> StoredChunk:
        """Convert a raw tuple result into a StoredChunk."""
        return StoredChunk(
            id=row[0],
            doc_id=row[1],
            title=row[2],
            section=row[3],
            text=row[4],
            strategy=row[5],
            start_char=row[6],
            end_char=row[7],
            embedding=row[8],
            keywords=row[9],
        )

    def vector_search(
        self,
        embedding: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[StoredChunk]:
        """Search chunks by cosine similarity to the query embedding."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                where = "WHERE 1=1"
                params: list[Any] = [str(embedding), top_k]
                if filters:
                    for key, value in filters.items():
                        where += " AND metadata->>%s = %s"
                        params.extend([key, value])
                sql = f"""
                    SELECT id, doc_id, title, section, text, strategy,
                           start_char, end_char, embedding, keywords
                    FROM chunks
                    {where}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """
                cur.execute(sql, params)
                return [self._row_to_chunk(row) for row in cur.fetchall()]

    def keyword_search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[StoredChunk]:
        """Full-text search using Postgres tsvector."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, doc_id, title, section, text, strategy,
                           start_char, end_char, embedding, keywords
                    FROM chunks
                    WHERE keywords @@ plainto_tsquery('english', %s)
                    ORDER BY ts_rank_cd(keywords, plainto_tsquery('english', %s)) DESC
                    LIMIT %s
                    """,
                    (query, query, top_k),
                )
                return [self._row_to_chunk(row) for row in cur.fetchall()]
