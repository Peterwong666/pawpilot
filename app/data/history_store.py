"""Analysis history store backed by PostgreSQL.

Records each scenario execution (input + output) so users can review past
analyses without re-running expensive LLM calls.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.core.config import get_settings
from app.rag.ingestion.store import _get_pool


class HistoryStore:
    """Stores and retrieves analysis history records."""

    def __init__(self) -> None:
        self.dsn = get_settings().database_url

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        with _get_pool(self.dsn).connection() as conn:
            yield conn

    def init_schema(self) -> None:
        """Create the analysis_history table if it does not exist."""
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS analysis_history (
                        id BIGSERIAL PRIMARY KEY,
                        scenario TEXT NOT NULL,
                        account_id TEXT NOT NULL DEFAULT 'default',
                        marketplace TEXT NOT NULL DEFAULT 'US',
                        input_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                        output_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                        summary TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_history_account
                    ON analysis_history (account_id, marketplace, created_at DESC)
                """)

    def add(
        self,
        scenario: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        summary: str = "",
        account_id: str = "default",
        marketplace: str = "US",
    ) -> int:
        """Insert a history record and return its ID."""
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analysis_history
                        (scenario, account_id, marketplace, input_data, output_data, summary)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        scenario,
                        account_id,
                        marketplace,
                        Jsonb(input_data),
                        Jsonb(output_data),
                        summary,
                    ),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0

    def list(
        self,
        account_id: str = "default",
        marketplace: str = "US",
        scenario: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent history records for an account, newest first."""
        sql = """
            SELECT id, scenario, account_id, marketplace, input_data,
                   output_data, summary, created_at
            FROM analysis_history
            WHERE account_id = %s AND marketplace = %s
        """
        params: list[Any] = [account_id, marketplace]
        if scenario:
            sql += " AND scenario = %s"
            params.append(scenario)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        rows: list[dict[str, Any]] = []
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                for r in cur.fetchall():
                    rows.append({
                        "id": r[0],
                        "scenario": r[1],
                        "account_id": r[2],
                        "marketplace": r[3],
                        "input_data": r[4],
                        "output_data": r[5],
                        "summary": r[6],
                        "created_at": r[7].isoformat() if r[7] else None,
                    })
        return rows

    def get(self, record_id: int) -> dict[str, Any] | None:
        """Return a single history record by ID."""
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, scenario, account_id, marketplace, input_data,
                           output_data, summary, created_at
                    FROM analysis_history WHERE id = %s
                    """,
                    (record_id,),
                )
                r = cur.fetchone()
                if not r:
                    return None
                return {
                    "id": r[0],
                    "scenario": r[1],
                    "account_id": r[2],
                    "marketplace": r[3],
                    "input_data": r[4],
                    "output_data": r[5],
                    "summary": r[6],
                    "created_at": r[7].isoformat() if r[7] else None,
                }
