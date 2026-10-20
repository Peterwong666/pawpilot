"""Inbox-directory connector: drop a CSV, get it ingested automatically.

Two run modes:

- **one-shot** — :func:`scan_inbox` processes every CSV currently in the
  inbox directory (the ``pawpilot ingest once`` CLI command);
- **watch** — :func:`watch_inbox` polls the directory on an interval and
  ingests new arrivals (the ``pawpilot ingest watch`` CLI command). A simple
  polling loop is used instead of watchdog so no extra dependency is needed.

File lifecycle::

    data/inbox/           ← drop exports here
    data/processed/       ← successfully imported files are archived here
    data/failed/          ← unparseable files land here (kept for inspection)

Format detection is two-stage: ERP order exports
(:mod:`app.data.erp_formats`) first, then the Amazon Seller Central /
Advertising reports (:mod:`app.data.csv_import`).
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.data.csv_import import CSVParseResult, parse_csv
from app.data.erp_formats import parse_erp_csv

#: callable(csv_type, df) — receives a parsed, canonical DataFrame.
IngestSink = Callable[[str, pd.DataFrame], None]

DEFAULT_INBOX_DIR = Path("data/inbox")
DEFAULT_PROCESSED_DIR = Path("data/processed")
DEFAULT_FAILED_DIR = Path("data/failed")


@dataclass(frozen=True)
class IngestOutcome:
    """Result of processing one file."""

    filename: str
    status: str  # "imported" | "failed"
    csv_type: str | None = None
    rows: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def parse_any_csv(content: bytes, filename: str) -> CSVParseResult:
    """Parse a dropped CSV: ERP order export first, Amazon reports as fallback."""
    try:
        return parse_erp_csv(content, filename=filename)
    except ValueError:
        pass
    try:
        return parse_csv(content, filename=filename)
    except UnicodeDecodeError:
        # parse_csv defaults to UTF-8; retry via the ERP decoder for GBK files
        # that turned out to be Amazon-format (edge case, kept explicit).
        from app.data.erp_formats import decode_csv_bytes

        text, _ = decode_csv_bytes(content)
        return parse_csv(text, filename=filename)


def _move(src: Path, dest_dir: Path) -> Path:
    """Move ``src`` into ``dest_dir``, suffixing the name when it already exists."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = dest_dir / f"{src.stem}.{stamp}{src.suffix}"
    shutil.move(str(src), str(dest))
    return dest


def ingest_file(path: Path, sink: IngestSink) -> IngestOutcome:
    """Parse one file and push the canonical rows into ``sink``."""
    try:
        parsed = parse_any_csv(path.read_bytes(), filename=path.name)
    except Exception as exc:  # noqa: BLE001 — surface any parse failure as an outcome
        return IngestOutcome(filename=path.name, status="failed", error=str(exc))
    sink(parsed.csv_type, parsed.df)
    return IngestOutcome(
        filename=path.name,
        status="imported",
        csv_type=parsed.csv_type,
        rows=len(parsed.df),
        warnings=list(parsed.warnings),
    )


def scan_inbox(
    inbox_dir: Path = DEFAULT_INBOX_DIR,
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    failed_dir: Path = DEFAULT_FAILED_DIR,
    sink: IngestSink | None = None,
) -> list[IngestOutcome]:
    """Process every ``*.csv`` currently in ``inbox_dir`` once.

    ``sink`` defaults to the Postgres-backed hybrid overlay (see
    :func:`default_sink`); tests inject a stub. Imported files are archived to
    ``processed_dir``; failures are moved to ``failed_dir``.
    """
    if sink is None:
        sink = default_sink()
    inbox_dir = Path(inbox_dir)
    if not inbox_dir.is_dir():
        return []
    outcomes: list[IngestOutcome] = []
    for path in sorted(inbox_dir.glob("*.csv")):
        outcome = ingest_file(path, sink)
        if outcome.status == "imported":
            _move(path, Path(processed_dir))
        else:
            _move(path, Path(failed_dir))
        outcomes.append(outcome)
    return outcomes


def watch_inbox(
    inbox_dir: Path = DEFAULT_INBOX_DIR,
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    failed_dir: Path = DEFAULT_FAILED_DIR,
    sink: IngestSink | None = None,
    interval_seconds: float = 5.0,
    max_cycles: int | None = None,
    on_cycle: Callable[[list[IngestOutcome]], None] | None = None,
) -> int:
    """Poll the inbox and ingest arrivals until interrupted.

    ``max_cycles`` bounds the loop (used by tests / smoke runs); ``None`` runs
    forever. ``on_cycle`` is invoked after every non-empty cycle, which lets
    the CLI print outcomes without this module depending on a console library.
    Returns the number of polling cycles executed.
    """
    if sink is None:
        sink = default_sink()
    Path(inbox_dir).mkdir(parents=True, exist_ok=True)
    cycles = 0
    while max_cycles is None or cycles < max_cycles:
        outcomes = scan_inbox(
            inbox_dir=inbox_dir,
            processed_dir=processed_dir,
            failed_dir=failed_dir,
            sink=sink,
        )
        cycles += 1
        if outcomes and on_cycle is not None:
            on_cycle(outcomes)
        if max_cycles is not None and cycles >= max_cycles:
            break
        time.sleep(interval_seconds)
    return cycles


def default_sink(
    account_id: str = "default",
    marketplace: str = "US",
) -> IngestSink:
    """Build a sink that overlays parsed rows via the Postgres hybrid store.

    Constructed lazily so importing this module (and running its tests) never
    requires a live database.
    """
    from app.data.hybrid_store import HybridDataStore

    store = HybridDataStore(account_id=account_id, marketplace=marketplace)

    def _sink(csv_type: str, df: pd.DataFrame) -> None:
        store.overlay(csv_type, df, account_id=account_id, marketplace=marketplace)

    return _sink
