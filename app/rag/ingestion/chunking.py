"""Chunking strategies for the RAG ingestion pipeline.

Three strategies are provided to support the evaluation experiments:

1. fixed        - simple fixed-size sliding window.
2. recursive    - split by paragraphs, then recursively by sentences.
3. hierarchical - preserve Markdown headers and chunk by sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings


@dataclass(frozen=True)
class Chunk:
    """A single chunk ready for embedding and storage."""

    text: str
    doc_id: str
    title: str
    section: str
    start_char: int
    end_char: int
    strategy: str


class Chunker(Protocol):
    def split(self, text: str, doc_id: str, title: str) -> list[Chunk]: ...


class FixedSizeChunker:
    """Fixed-size chunks with overlap."""

    def __init__(self, size: int | None = None, overlap: int | None = None) -> None:
        if size is None or overlap is None:
            settings = get_settings()
        self.size = size if size is not None else settings.chunk_size
        self.overlap = overlap if overlap is not None else settings.chunk_overlap

    def split(self, text: str, doc_id: str, title: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        step = max(1, self.size - self.overlap)
        for i, start in enumerate(range(0, len(text), step)):
            end = min(start + self.size, len(text))
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        doc_id=doc_id,
                        title=title,
                        section=f"fixed_chunk_{i + 1}",
                        start_char=start,
                        end_char=end,
                        strategy="fixed",
                    )
                )
            if end == len(text):
                break
        return chunks


class RecursiveChunker:
    """Split by paragraphs first, then recursively split large paragraphs."""

    def __init__(self, size: int | None = None, overlap: int | None = None) -> None:
        if size is None or overlap is None:
            settings = get_settings()
        self.size = size if size is not None else settings.chunk_size
        self.overlap = overlap if overlap is not None else settings.chunk_overlap

    def _split_paragraph(self, paragraph: str) -> list[str]:
        if len(paragraph) <= self.size:
            return [paragraph]
        # Split by sentence-ish boundaries.
        sentences = re.split(r"(?<=[.!?。！？])\s+", paragraph)
        parts: list[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) <= self.size:
                current = f"{current} {sentence}".strip()
            else:
                if current:
                    parts.append(current)
                current = sentence
        if current:
            parts.append(current)
        return parts

    def split(self, text: str, doc_id: str, title: str) -> list[Chunk]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        chunks: list[Chunk] = []
        for para_idx, paragraph in enumerate(paragraphs):
            for sub_idx, sub in enumerate(self._split_paragraph(paragraph)):
                chunks.append(
                    Chunk(
                        text=sub,
                        doc_id=doc_id,
                        title=title,
                        section=f"para_{para_idx + 1}_sub_{sub_idx + 1}",
                        start_char=0,
                        end_char=0,
                        strategy="recursive",
                    )
                )
        return chunks


class HierarchicalChunker:
    """Preserve Markdown headings and chunk within each section."""

    _HEADER_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)

    def __init__(self, size: int | None = None, overlap: int | None = None) -> None:
        if size is None or overlap is None:
            settings = get_settings()
        self.size = size if size is not None else settings.chunk_size
        self.overlap = overlap if overlap is not None else settings.chunk_overlap

    def split(self, text: str, doc_id: str, title: str) -> list[Chunk]:
        matches = list(self._HEADER_RE.finditer(text))
        if not matches:
            # Fallback to fixed-size if no headers.
            return FixedSizeChunker(self.size, self.overlap).split(text, doc_id, title)

        chunks: list[Chunk] = []
        positions = [(m.start(), m.group(2).strip()) for m in matches]
        positions.append((len(text), "_end"))

        for i in range(len(positions) - 1):
            start, header = positions[i]
            end = positions[i + 1][0]
            section_text = text[start:end].strip()
            if not section_text:
                continue
            # Further split long sections using fixed-size chunker.
            sub_chunks = FixedSizeChunker(self.size, self.overlap).split(
                section_text, doc_id, title
            )
            for idx, sub in enumerate(sub_chunks):
                chunks.append(
                    Chunk(
                        text=sub.text,
                        doc_id=doc_id,
                        title=title,
                        section=f"{header}#{idx + 1}",
                        start_char=start + sub.start_char,
                        end_char=min(start + sub.end_char, end),
                        strategy="hierarchical",
                    )
                )
        return chunks


_STRATEGIES: dict[str, type[Chunker]] = {
    "fixed": FixedSizeChunker,
    "recursive": RecursiveChunker,
    "hierarchical": HierarchicalChunker,
}


def get_chunker(strategy: str) -> Chunker:
    if strategy not in _STRATEGIES:
        raise ValueError(f"Unknown chunking strategy {strategy!r}. Choose from {_STRATEGIES.keys()}")
    return _STRATEGIES[strategy]()
