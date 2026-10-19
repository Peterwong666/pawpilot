"""Lightweight in-process request statistics (observability, P4).

A single process-wide ``StatsCollector`` aggregates what the API middleware
observes: request counts, latency, retrieval hit rate and token usage when the
scenario layer reports it. Kept deliberately simple (in-memory, no external
dependency) — OpenTelemetry export is left as follow-up work (see README
roadmap).
"""

from __future__ import annotations

import threading
import time
from typing import Any


class StatsCollector:
    """Thread-safe in-memory aggregator for API request metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.total_requests = 0
        self.total_latency_ms = 0.0
        # Requests that performed retrieval, and how many of them hit ≥1 chunk.
        self.retrieval_requests = 0
        self.retrieval_hits = 0
        # Token usage summed over scenarios that report it.
        self.token_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.by_path: dict[str, int] = {}

    def record(
        self,
        *,
        method: str,
        path: str,
        status: int,
        latency_ms: float,
        retrieval_hit: bool | None = None,
        token_usage: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self.total_requests += 1
            self.total_latency_ms += latency_ms
            route_key = f"{method} {path}"
            self.by_path[route_key] = self.by_path.get(route_key, 0) + 1
            if retrieval_hit is not None:
                self.retrieval_requests += 1
                if retrieval_hit:
                    self.retrieval_hits += 1
            if token_usage:
                calls = int(token_usage.get("calls") or 0)
                self.token_calls += calls
                self.input_tokens += int(token_usage.get("input_tokens") or 0)
                self.output_tokens += int(token_usage.get("output_tokens") or 0)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg_latency = (
                round(self.total_latency_ms / self.total_requests, 2)
                if self.total_requests
                else 0.0
            )
            hit_rate = (
                round(self.retrieval_hits / self.retrieval_requests, 4)
                if self.retrieval_requests
                else None
            )
            return {
                "requests_total": self.total_requests,
                "avg_latency_ms": avg_latency,
                "retrieval_requests": self.retrieval_requests,
                "retrieval_hits": self.retrieval_hits,
                "retrieval_hit_rate": hit_rate,
                "token_usage": {
                    "calls": self.token_calls,
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                },
                "by_path": dict(sorted(self.by_path.items())),
                "started_at": self.started_at,
                "uptime_seconds": round(time.time() - self.started_at, 1),
            }


# Process-wide singleton consumed by the API middleware and the /stats endpoint.
STATS = StatsCollector()
