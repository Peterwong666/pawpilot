"""Simple Markdown corpus parser.

Corpus files are assumed to be UTF-8 Markdown. We strip comments, normalize
whitespace, and split into coherent text chunks that preserve front-matter metadata.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    """A single source document."""

    id: str
    source: str
    title: str
    text: str
    metadata: dict[str, str]


def _clean_markdown(text: str) -> str:
    """Normalize whitespace and remove HTML comments."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_title(text: str) -> str:
    first_line = text.split("\n", 1)[0]
    if first_line.startswith("# "):
        return first_line[2:].strip()
    if first_line.startswith("## "):
        return first_line[3:].strip()
    return "Untitled"


def parse_file(path: Path) -> Document:
    raw = path.read_text(encoding="utf-8")
    cleaned = _clean_markdown(raw)
    relative = path.relative_to(path.parent.parent.parent).as_posix()
    return Document(
        id=relative,
        source=str(path),
        title=_extract_title(cleaned),
        text=cleaned,
        metadata={
            "filename": path.name,
            "category": path.parent.name,
        },
    )


def parse_directory(root: Path, glob: str = "**/*.md") -> list[Document]:
    """Recursively parse all Markdown files under root."""
    docs: list[Document] = []
    for path in sorted(root.glob(glob)):
        if path.is_file():
            docs.append(parse_file(path))
    return docs


def parse_documents(paths: Iterable[Path]) -> list[Document]:
    """Parse an explicit list of files."""
    docs: list[Document] = []
    for path in paths:
        if path.is_file() and path.suffix == ".md":
            docs.append(parse_file(path))
    return docs
