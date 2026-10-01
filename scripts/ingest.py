"""CLI to ingest the knowledge base."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich import print

from app.rag.ingestion.pipeline import run_ingestion

app = typer.Typer()


@app.command()
def ingest(
    root: Path = Path("data/knowledge_base"),
    strategy: str = "hierarchical",
    reset: bool = False,
) -> None:
    stats = asyncio.run(run_ingestion(root, strategy=strategy, reset=reset))
    print(f"[green]Ingested:[/green] {stats}")


if __name__ == "__main__":
    app()
