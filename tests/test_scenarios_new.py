"""Tests for the three new scenarios with a mocked LLM generator.

The deterministic tool layer (digest/diagnosis/VOC) runs against real simulated data;
only the LLM narration is mocked, proving the numbers never depend on the LLM.
"""

from __future__ import annotations

import pytest

from app.agent.tools import ToolRegistry
from app.core.mock_llm import DemoGenerator, StaticDemoRetriever
from app.data.simulated import ANOMALY_SALES_SKU, SimulatedDataStore
from app.scenarios.compliance_engine import ComplianceRuleEngine
from app.scenarios.ops_digest import OpsDailyDigestScenario
from app.scenarios.product_dev import ProductDevScenario
from app.scenarios.sales_diagnosis import SalesDiagnosisScenario


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry.__new__(ToolRegistry)
    reg.data_store = SimulatedDataStore()
    reg.rule_engine = ComplianceRuleEngine()
    return reg


@pytest.fixture()
def mock_generator() -> DemoGenerator:
    return DemoGenerator()


async def test_ops_digest_scenario(registry: ToolRegistry, mock_generator: DemoGenerator) -> None:
    scenario = OpsDailyDigestScenario(
        retriever=StaticDemoRetriever(), generator=mock_generator, registry=registry
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
    assert result["usage"]["calls"] == 1


async def test_sales_diagnosis_scenario(registry: ToolRegistry, mock_generator: DemoGenerator) -> None:
    scenario = SalesDiagnosisScenario(
        retriever=StaticDemoRetriever(), generator=mock_generator, registry=registry
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


async def test_sales_diagnosis_normal_sku(registry: ToolRegistry, mock_generator: DemoGenerator) -> None:
    scenario = SalesDiagnosisScenario(
        retriever=StaticDemoRetriever(), generator=mock_generator, registry=registry
    )
    result = await scenario.diagnose("PP-HR-201", days=14)
    assert result["diagnosis"]["status"] == "normal"
    assert "指标对比" in result["final_answer"]


async def test_product_dev_scenario(registry: ToolRegistry, mock_generator: DemoGenerator) -> None:
    scenario = ProductDevScenario(
        retriever=StaticDemoRetriever(), generator=mock_generator, registry=registry
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
