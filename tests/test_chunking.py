"""Tests for chunking strategies."""

from __future__ import annotations

import pytest

from app.rag.ingestion.chunking import (
    FixedSizeChunker,
    HierarchicalChunker,
    RecursiveChunker,
)

SAMPLE_TEXT = """# Title

First paragraph with enough text to matter for chunking. It should be processed as a unit.

## Section A

Section A paragraph one. Section A paragraph two with more words to ensure we have content.

## Section B

Section B paragraph one.
"""


def test_fixed_size_chunker_produces_chunks() -> None:
    chunker = FixedSizeChunker(size=50, overlap=10)
    chunks = chunker.split(SAMPLE_TEXT, doc_id="doc1", title="Title")
    assert len(chunks) > 0
    assert all(c.strategy == "fixed" for c in chunks)
    assert all(c.text for c in chunks)


def test_recursive_chunker_respects_paragraphs() -> None:
    chunker = RecursiveChunker(size=200, overlap=20)
    chunks = chunker.split(SAMPLE_TEXT, doc_id="doc1", title="Title")
    assert len(chunks) >= 2
    assert all(c.strategy == "recursive" for c in chunks)


def test_hierarchical_chunker_preserves_headers() -> None:
    chunker = HierarchicalChunker(size=200, overlap=20)
    chunks = chunker.split(SAMPLE_TEXT, doc_id="doc1", title="Title")
    assert len(chunks) >= 1
    assert any("Section A" in c.section for c in chunks)


def test_unknown_strategy_raises() -> None:
    from app.rag.ingestion.chunking import get_chunker

    with pytest.raises(ValueError):
        get_chunker("does_not_exist")
