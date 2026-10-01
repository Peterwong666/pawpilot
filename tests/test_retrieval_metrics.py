"""Tests for deterministic retrieval metrics."""

from __future__ import annotations

import math

from eval.metrics import mrr, ndcg_at_k, recall_at_k


def test_recall_perfect() -> None:
    assert recall_at_k(["a", "b"], ["a", "b", "c"]) == 1.0


def test_recall_partial() -> None:
    assert recall_at_k(["a", "b"], ["a", "c"]) == 0.5


def test_recall_at_k_truncates() -> None:
    assert recall_at_k(["a", "b"], ["a", "c", "d"], k=2) == 0.5


def test_mrr_first() -> None:
    assert mrr(["a"], ["a", "b"]) == 1.0


def test_mrr_third() -> None:
    assert mrr(["a"], ["b", "c", "a"]) == 1.0 / 3.0


def test_mrr_miss() -> None:
    assert mrr(["a"], ["b", "c"]) == 0.0


def test_ndcg_perfect() -> None:
    k = 2
    dcg = 1.0 / math.log2(1 + 1) + 1.0 / math.log2(2 + 1)
    idcg = dcg
    assert ndcg_at_k(["a", "b"], ["a", "b"], k) == dcg / idcg


def test_ndcg_zero() -> None:
    assert ndcg_at_k(["a"], ["b", "c", "d"], 3) == 0.0
