"""Tests for the three new scenarios with a mocked LLM generator.

The deterministic tool layer (digest/diagnosis/VOC) runs against real simulated data;
only the LLM narration is mocked, proving the numbers never depend on the LLM.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.agent.tools import ToolRegistry
from app.data.simulated import ANOMALY_SALES_SKU, SimulatedDataStore
from app.scenarios.compliance_engine import ComplianceRuleEngine
from app.scenarios.ops_digest import OpsDailyDigestScenario
from app.scenarios.product_dev import ProductDevScenario
from app.scenarios.sales_diagnosis import SalesDiagnosisScenario


class MockGenerator:
    """Stand-in for Generator: returns canned Chinese narration, records calls."""

    provider = "mock"
    model = "mock-model"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def summarize_ops_digest(self, digest: dict, knowledge: list) -> dict[str, Any]:
        self.calls.append("summarize_ops_digest")
        assert digest["alerts"], "digest must contain alerts before narration"
        return {"summary": "今日需优先处理 3 项告警……", "usage": {"calls": 1}}

    async def narrate_sales_diagnosis(self, sku: str, diagnosis: dict, knowledge: list) -> dict[str, Any]:
        self.calls.append("narrate_sales_diagnosis")
        return {"narrative": f"{sku} 销量下滑的主要原因是评分下滑与广告暂停……", "usage": {"calls": 1}}

    async def synthesize_product_dev(
        self, product_type: str, voc: dict, product_context: str, knowledge: list
    ) -> dict[str, Any]:
        self.calls.append("synthesize_product_dev")
        assert voc["themes"], "VOC themes must be aggregated before synthesis"
        return {"report": "竞品最集中的未满足需求是……建议改进规格……", "usage": {"calls": 1}}


class MockRetriever:
    async def retrieve_texts(self, query: str, final_top_k: int = 5) -> list[dict[str, Any]]:
        return [
            {"doc_id": "negative_review_response_sop", "section": "Templates", "text": "模板 T1..."},
        ]


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry.__new__(ToolRegistry)
    reg.data_store = SimulatedDataStore()
    reg.rule_engine = ComplianceRuleEngine()
    return reg


@pytest.fixture()
def mock_generator() -> MockGenerator:
    return MockGenerator()


async def test_ops_digest_scenario(registry: ToolRegistry, mock_generator: MockGenerator) -> None:
    scenario = OpsDailyDigestScenario(
        retriever=MockRetriever(), generator=mock_generator, registry=registry
    )
    result = await scenario.generate()

    assert mock_generator.calls == ["summarize_ops_digest"]
    assert "运营日报" in result["final_answer"]
    assert "执行摘要" in result["final_answer"]
    assert "今日需优先处理" in result["final_answer"]  # LLM summary embedded
    # Deterministic alerts embedded in the report.
    alert_pairs = {(a["type"], a["sku"]) for a in result["digest"]["alerts"]}
    assert ("sales_drop", ANOMALY_SALES_SKU) in alert_pairs
    assert ("stockout_risk", "PP-SB-302") in alert_pairs
    # Portfolio table covers all six SKUs.
    assert result["final_answer"].count("\n| PP-") == 6
    assert result["usage"] == {"calls": 1}


async def test_sales_diagnosis_scenario(registry: ToolRegistry, mock_generator: MockGenerator) -> None:
    scenario = SalesDiagnosisScenario(
        retriever=MockRetriever(), generator=mock_generator, registry=registry
    )
    result = await scenario.diagnose(ANOMALY_SALES_SKU, days=14)

    assert mock_generator.calls == ["narrate_sales_diagnosis"]
    assert "销量异动诊断" in result["final_answer"]
    assert "销量下滑的主要原因是评分下滑与广告暂停" in result["final_answer"]
    # Ground-truth causes surfaced with Chinese labels.
    assert "广告预算削减" in result["final_answer"]
    assert "评分下滑拖累转化" in result["final_answer"]
    # Deterministic evidence table present.
    assert "指标对比" in result["final_answer"]
    assert result["diagnosis"]["status"] == "anomaly_detected"


async def test_sales_diagnosis_normal_sku(registry: ToolRegistry, mock_generator: MockGenerator) -> None:
    scenario = SalesDiagnosisScenario(
        retriever=MockRetriever(), generator=mock_generator, registry=registry
    )
    result = await scenario.diagnose("PP-HR-201", days=14)
    assert result["diagnosis"]["status"] == "normal"
    assert "指标对比" in result["final_answer"]


async def test_product_dev_scenario(registry: ToolRegistry, mock_generator: MockGenerator) -> None:
    scenario = ProductDevScenario(
        retriever=MockRetriever(), generator=mock_generator, registry=registry
    )
    result = await scenario.analyze("rope toy")

    assert mock_generator.calls == ["synthesize_product_dev"]
    assert "产品改进机会报告" in result["final_answer"]
    assert "竞品最集中的未满足需求" in result["final_answer"]
    assert "未满足需求数据" in result["final_answer"]
    # Profit context from the representative SKU.
    assert result["profit"]["sku"] == "PP-RT-102"
    assert "盈亏平衡价" in result["final_answer"]
    # VOC negative themes (not the positive bucket) listed in the table.
    assert "fraying" in result["final_answer"] or "squeaker_failure" in result["final_answer"]
