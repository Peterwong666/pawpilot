"""PawPilot CLI — operational-data ingestion commands.

Registered as the ``pawpilot`` console script (see ``[project.scripts]`` in
pyproject.toml)::

    pawpilot ingest once --dir data/inbox      # one-shot scan of the inbox dir
    pawpilot ingest watch --dir data/inbox     # poll-and-ingest new arrivals
    pawpilot ingest formats                    # list detectable export formats

The knowledge-base ingestion CLI stays in ``scripts/ingest.py``; this entry
point covers operational CSV data only.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich import print

from app.data.erp_formats import supported_erp_formats
from app.data.inbox_ingest import (
    DEFAULT_FAILED_DIR,
    DEFAULT_INBOX_DIR,
    DEFAULT_PROCESSED_DIR,
    IngestOutcome,
    default_sink,
    scan_inbox,
    watch_inbox,
)

app = typer.Typer(help="PawPilot operations CLI.")
ingest_app = typer.Typer(help="CSV ingestion connector (inbox directory).")
app.add_typer(ingest_app, name="ingest")


def _print_outcomes(outcomes: list[IngestOutcome]) -> None:
    for o in outcomes:
        if o.status == "imported":
            print(
                f"[green]✓ {o.filename}[/green] — {o.rows} rows imported "
                f"(type: {o.csv_type})"
            )
            for warning in o.warnings:
                print(f"  [yellow]warning:[/yellow] {warning}")
        else:
            print(f"[red]✗ {o.filename}[/red] — {o.error}")


@ingest_app.command("once")
def ingest_once(
    dir: Path = typer.Option(DEFAULT_INBOX_DIR, help="Inbox directory to scan."),
    processed_dir: Path = typer.Option(DEFAULT_PROCESSED_DIR, help="Archive directory for imported files."),
    failed_dir: Path = typer.Option(DEFAULT_FAILED_DIR, help="Directory for unparseable files."),
    account_id: str = typer.Option("default", help="Account ID attached to imported rows."),
    marketplace: str = typer.Option("US", help="Marketplace attached to imported rows."),
) -> None:
    """Scan the inbox directory once: import every CSV, then archive."""
    sink = default_sink(account_id=account_id, marketplace=marketplace)
    outcomes = scan_inbox(
        inbox_dir=dir, processed_dir=processed_dir, failed_dir=failed_dir, sink=sink
    )
    if not outcomes:
        print(f"[dim]{dir} is empty — nothing to ingest.[/dim]")
        return
    _print_outcomes(outcomes)
    imported = sum(1 for o in outcomes if o.status == "imported")
    failed = len(outcomes) - imported
    print(f"Done: {imported} imported, {failed} failed.")
    if failed:
        raise typer.Exit(code=1)


@ingest_app.command("watch")
def ingest_watch(
    dir: Path = typer.Option(DEFAULT_INBOX_DIR, help="Inbox directory to poll."),
    processed_dir: Path = typer.Option(DEFAULT_PROCESSED_DIR, help="Archive directory for imported files."),
    failed_dir: Path = typer.Option(DEFAULT_FAILED_DIR, help="Directory for unparseable files."),
    interval: float = typer.Option(5.0, help="Polling interval in seconds."),
    account_id: str = typer.Option("default", help="Account ID attached to imported rows."),
    marketplace: str = typer.Option("US", help="Marketplace attached to imported rows."),
) -> None:
    """Poll the inbox directory and auto-ingest CSVs as they arrive."""
    sink = default_sink(account_id=account_id, marketplace=marketplace)
    print(f"Watching {dir} every {interval:.0f}s (Ctrl-C to stop)…")
    try:
        watch_inbox(
            inbox_dir=dir,
            processed_dir=processed_dir,
            failed_dir=failed_dir,
            sink=sink,
            interval_seconds=interval,
            on_cycle=_print_outcomes,
        )
    except KeyboardInterrupt:
        print("Stopped.")


@ingest_app.command("formats")
def ingest_formats() -> None:
    """List the ERP export formats recognised by the inbox connector."""
    for f in supported_erp_formats():
        print(f"[bold]{f['name']}[/bold] ({f['format_id']} → {f['csv_type']})")
        print(f"  signature headers: {', '.join(f['signature_headers'])}")  # type: ignore[attr-defined]


if __name__ == "__main__":
    app()
