"""Tests for ERP order-export format detection, decoding and column mapping."""

from __future__ import annotations

import pytest

from app.data.erp_formats import (
    ERP_FORMATS,
    JINGDONG_ORDER,
    TAOBAO_ORDER,
    decode_csv_bytes,
    detect_erp_format,
    parse_erp_csv,
    supported_erp_formats,
)

TAOBAO_CSV = """订单编号,买家会员名,宝贝标题,商家编码,购买数量,买家实际支付金额,订单状态,订单创建时间
TB1001,buyer_a,狗狗棉绳玩具,pp-rt-102,2,¥29.98,交易成功,2024-10-01 10:23:00
TB1002,buyer_b,狗狗棉绳玩具,PP-RT-102,1,¥14.99,交易成功,2024-10-01 12:41:00
TB1003,buyer_c,宠物慢食碗,PP-SB-302,1,¥16.99,交易关闭,2024-10-02 09:05:00
TB1004,buyer_d,宠物慢食碗,PP-SB-302,3,¥50.97,交易成功,2024-10-02 15:30:00
"""

JINGDONG_CSV = """订单号,商品名称,商品编号,商品数量,实付金额,订单状态,下单时间
JD2001,狗狗咬胶玩具,pp-rt-101,1,9.99,已完成,2024-10-03 08:15:00
JD2002,宠物胸背带,PP-HR-201,2,25.98,已完成,2024-10-03 11:02:00
JD2003,宠物胸背带,PP-HR-201,1,12.99,已取消,2024-10-04 14:22:00
"""

UNKNOWN_HEADERS_CSV = """foo,bar,baz
1,2,3
"""


def test_decode_utf8_and_gbk() -> None:
    text, enc = decode_csv_bytes("商家编码,数量\nA1,2\n".encode())
    assert enc == "utf-8-sig"
    assert "商家编码" in text

    text, enc = decode_csv_bytes("商家编码,数量\nA1,2\n".encode("gbk"))
    assert enc == "gb18030"
    assert "商家编码" in text


def test_decode_rejects_binary_garbage() -> None:
    with pytest.raises(ValueError, match="Could not decode"):
        decode_csv_bytes(b"\xff\xfe\x00\x01\x02")


def test_detect_taobao_format() -> None:
    assert detect_erp_format(TAOBAO_CSV.splitlines()[0].split(",")) is TAOBAO_ORDER


def test_detect_jingdong_format() -> None:
    assert detect_erp_format(JINGDONG_CSV.splitlines()[0].split(",")) is JINGDONG_ORDER


def test_detect_unknown_returns_none() -> None:
    assert detect_erp_format(["col_a", "col_b"]) is None


def test_parse_taobao_csv_aggregates_orders_to_daily_sales() -> None:
    result = parse_erp_csv(TAOBAO_CSV, filename="taobao.csv")
    assert result.csv_type == "sales"
    assert result.detection.confidence == "high"

    df = result.df
    assert set(df.columns) == {"sku", "date", "units_sold", "revenue_usd"}

    # Two successful PP-RT-102 orders on 2024-10-01 are summed into one row.
    rt = df[(df["sku"] == "PP-RT-102") & (df["date"].astype(str) == "2024-10-01")]
    assert len(rt) == 1
    assert rt["units_sold"].iloc[0] == 3
    assert float(rt["revenue_usd"].iloc[0]) == pytest.approx(44.97)

    # The 交易关闭 (cancelled) order is dropped; only the successful row remains.
    sb = df[df["sku"] == "PP-SB-302"]
    assert len(sb) == 1
    assert sb["units_sold"].iloc[0] == 3
    assert any("cancelled" in w for w in result.warnings)


def test_parse_jingdong_csv_from_gbk_bytes() -> None:
    result = parse_erp_csv(JINGDONG_CSV.encode("gbk"), filename="jd.csv")
    assert result.csv_type == "sales"
    df = result.df
    # 已取消 order excluded; two completed orders on the same day stay separate
    # by SKU but same-day same-SKU orders would aggregate.
    assert set(df["sku"]) == {"PP-RT-101", "PP-HR-201"}
    hr = df[df["sku"] == "PP-HR-201"]
    assert hr["units_sold"].iloc[0] == 2
    assert any("gb18030" in w for w in result.warnings)


def test_parse_unknown_headers_raises() -> None:
    with pytest.raises(ValueError, match="Could not detect ERP format"):
        parse_erp_csv(UNKNOWN_HEADERS_CSV, filename="unknown.csv")


def test_supported_formats_metadata() -> None:
    formats = supported_erp_formats()
    ids = {f["format_id"] for f in formats}
    assert ids == {f.format_id for f in ERP_FORMATS}
    assert all(f["csv_type"] == "sales" for f in formats)
