"""CLI to ingest the knowledge base."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich import print

from app.core.config import get_settings
from app.rag.ingestion.pipeline import run_ingestion
from app.rag.retrieval.demo import DEMO_CORPUS_ROOT, DemoRetriever

app = typer.Typer()


@app.command()
def ingest(
    root: Path = Path("data/knowledge_base"),
    strategy: str = "hierarchical",
    reset: bool = False,
) -> None:
    # Fail fast on missing API keys with actionable guidance, before any
    # embedding client construction can raise a misleading SDK error.
    settings = get_settings()
    try:
        settings.validate_runtime()
    except ValueError as exc:
        print(f"[red]Configuration error:[/red]\n{exc}")
        raise typer.Exit(code=1) from exc
    if settings.demo_mode:
        # Demo mode: embed the bundled corpus into the local in-memory store.
        # (The API also ingests automatically on startup; this CLI run is a
        # convenient warm-up / sanity check.)
        count = asyncio.run(DemoRetriever(corpus_root=DEMO_CORPUS_ROOT).ensure_ingested())
        print(
            f"[green]Demo mode:[/green] ingested {count} chunks from {DEMO_CORPUS_ROOT} "
            "into the local in-memory store (no Postgres / API key needed)."
        )
        return
    stats = asyncio.run(run_ingestion(root, strategy=strategy, reset=reset))
    print(f"[green]Ingested:[/green] {stats}")


if __name__ == "__main__":
    app()
