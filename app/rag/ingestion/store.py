"""Vector and full-text storage layer backed by PostgreSQL + pgvector.

This module owns the schema, indexing, and CRUD operations for chunks. It keeps both vector
search (pgvector) and keyword search (tsvector) in one table to simplify operations and
self-hosting.
"""

from __future__ import annotations

import atexit
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

# Process-wide connection pools, keyed by DSN. Opening a psycopg connection costs
# a TCP + auth round-trip, and a single retrieval request issues several queries,
# so pooling removes that overhead from the hot path.
_pools: dict[str, ConnectionPool] = {}
_pools_lock = threading.Lock()
_atexit_registered = False


def _get_pool(dsn: str) -> ConnectionPool:
    """Return the shared pool for ``dsn``, creating it lazily on first use."""
    global _atexit_registered
    pool = _pools.get(dsn)
    if pool is not None:
        return pool
    with _pools_lock:
        pool = _pools.get(dsn)
        if pool is None:
            settings = get_settings()
            pool = ConnectionPool(
                conninfo=dsn,
                min_size=1,
                max_size=8,
                timeout=settings.db_timeout,
                open=True,
            )
            _pools[dsn] = pool
            # Registered after construction so this handler runs before the pool's
            # own atexit hook, letting worker threads shut down without warnings.
            if not _atexit_registered:
                atexit.register(close_pools)
                _atexit_registered = True
    return pool


def close_pools() -> None:
    """Close every pool. Called on application shutdown."""
    with _pools_lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()


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

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        """Borrow a pooled connection, returning it to the pool afterwards."""
        with _get_pool(self.dsn).connection() as conn:
            yield conn

    def init_schema(self) -> None:
        """Create extensions, table, and indexes."""
        with self._connection() as conn:
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
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE chunks RESTART IDENTITY;")
            conn.commit()

    def count_chunks(self) -> int:
        """Return the number of stored chunks (used by health checks)."""
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM chunks;")
                row = cur.fetchone()
                return int(row[0]) if row else 0

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
        with self._connection() as conn:
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
        with self._connection() as conn:
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
        with self._connection() as conn:
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
