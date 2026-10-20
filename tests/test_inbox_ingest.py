"""Tests for the inbox-directory ingestion connector (P7).

All tests are hermetic: CSVs are written into ``tmp_path`` and the Postgres
sink is replaced by an in-memory stub.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.data.inbox_ingest import ingest_file, scan_inbox, watch_inbox

AMAZON_SALES_CSV = """SKU,Date,Sessions,Units Ordered,Ordered Product Sales,Unit Session Percentage
PP-RT-102,2024-10-01,120,12,"$179.88",10.00%
PP-SB-302,2024-10-01,95,8,"$135.92",8.42%
"""

TAOBAO_CSV = """订单编号,买家会员名,宝贝标题,商家编码,购买数量,买家实际支付金额,订单状态,订单创建时间
TB1001,buyer_a,狗狗棉绳玩具,PP-RT-102,2,29.98,交易成功,2024-10-01 10:23:00
"""

BROKEN_CSV = """foo,bar,baz
1,2,3
"""


class StubSink:
    """In-memory replacement for the Postgres hybrid overlay."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, pd.DataFrame]] = []

    def __call__(self, csv_type: str, df: pd.DataFrame) -> None:
        self.calls.append((csv_type, df))


def _write(path: Path, content: str, encoding: str = "utf-8") -> Path:
    path.write_bytes(content.encode(encoding))
    return path


def test_ingest_file_amazon_format() -> None:
    sink = StubSink()
    path = _write(Path("/tmp") / "biz_report.csv", AMAZON_SALES_CSV)
    try:
        outcome = ingest_file(path, sink)
        assert outcome.status == "imported"
        assert outcome.csv_type == "sales"
        assert outcome.rows == 2
        assert sink.calls[0][0] == "sales"
    finally:
        path.unlink(missing_ok=True)


def test_ingest_file_erp_format_gbk() -> None:
    sink = StubSink()
    path = _write(Path("/tmp") / "taobao.csv", TAOBAO_CSV, encoding="gbk")
    try:
        outcome = ingest_file(path, sink)
        assert outcome.status == "imported"
        assert outcome.csv_type == "sales"
        assert outcome.rows == 1
        df = sink.calls[0][1]
        assert df["sku"].iloc[0] == "PP-RT-102"
        assert df["units_sold"].iloc[0] == 2
    finally:
        path.unlink(missing_ok=True)


def test_ingest_file_unparseable_reports_failure() -> None:
    sink = StubSink()
    path = _write(Path("/tmp") / "garbage.csv", BROKEN_CSV)
    try:
        outcome = ingest_file(path, sink)
        assert outcome.status == "failed"
        assert outcome.error is not None
        assert sink.calls == []
    finally:
        path.unlink(missing_ok=True)


def test_scan_inbox_processes_and_archives(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    inbox.mkdir()
    _write(inbox / "sales.csv", AMAZON_SALES_CSV)
    _write(inbox / "taobao.csv", TAOBAO_CSV, encoding="gbk")
    _write(inbox / "broken.csv", BROKEN_CSV)

    sink = StubSink()
    outcomes = scan_inbox(inbox_dir=inbox, processed_dir=processed, failed_dir=failed, sink=sink)

    by_name = {o.filename: o for o in outcomes}
    assert by_name["sales.csv"].status == "imported"
    assert by_name["taobao.csv"].status == "imported"
    assert by_name["broken.csv"].status == "failed"

    # Imported files archived; failures quarantined; inbox left empty.
    assert {p.name for p in processed.glob("*.csv")} == {"sales.csv", "taobao.csv"}
    assert {p.name for p in failed.glob("*.csv")} == {"broken.csv"}
    assert list(inbox.glob("*.csv")) == []

    # Two imports reached the sink (Amazon sales + ERP sales).
    assert [c[0] for c in sink.calls] == ["sales", "sales"]

    # A second scan is a no-op (idempotent).
    assert scan_inbox(inbox_dir=inbox, processed_dir=processed, failed_dir=failed, sink=sink) == []
    assert len(sink.calls) == 2


def test_scan_inbox_missing_directory_returns_empty(tmp_path: Path) -> None:
    outcomes = scan_inbox(
        inbox_dir=tmp_path / "nope",
        processed_dir=tmp_path / "p",
        failed_dir=tmp_path / "f",
        sink=StubSink(),
    )
    assert outcomes == []


def test_watch_inbox_picks_up_new_files(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    sink = StubSink()
    seen: list[list[str]] = []

    # Cycle 1 creates the inbox dir; drop a file between cycles by pre-seeding
    # via a callback that fires after cycle 1's (empty) scan.
    def _on_cycle(outcomes) -> None:  # type: ignore[no-untyped-def]
        seen.append([o.filename for o in outcomes])

    inbox.mkdir()
    _write(inbox / "later.csv", AMAZON_SALES_CSV)

    cycles = watch_inbox(
        inbox_dir=inbox,
        processed_dir=processed,
        failed_dir=failed,
        sink=sink,
        interval_seconds=0.01,
        max_cycles=2,
        on_cycle=_on_cycle,
    )
    assert cycles == 2
    assert seen == [["later.csv"]]
    assert (processed / "later.csv").exists()
