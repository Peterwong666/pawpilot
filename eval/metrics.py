"""Deterministic retrieval metrics used by the evaluation runner.

Kept as pure functions so they can be tested without instantiating any API client.
"""

from __future__ import annotations

import math


def recall_at_k(gold: list[str], retrieved: list[str], k: int | None = None) -> float:
    if not gold:
        return 0.0
    retrieved_k = retrieved[:k] if k is not None else retrieved
    hits = len(set(gold) & set(retrieved_k))
    return hits / len(gold)


def mrr(gold: list[str], retrieved: list[str]) -> float:
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in gold:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(gold: list[str], retrieved: list[str], k: int) -> float:
    if not gold:
        return 0.0
    dcg = 0.0
    for rank, doc_id in enumerate(retrieved[:k], start=1):
        if doc_id in gold:
            dcg += 1.0 / math.log2(rank + 1)
    ideal_hits = min(len(gold), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0
