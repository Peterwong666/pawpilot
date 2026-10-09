"""Streamlit demo UI for PawPilot.

Six scenario tabs plus data upload:
1. Policy Q&A — ask Amazon policy questions.
2. Listing Generator — generate and review a listing from product info.
3. Review Analysis — analyze simulated reviews for a SKU.
4. Ops Daily Digest — portfolio-level daily operations briefing (Chinese).
5. Sales Diagnosis — attribute a SKU's sales change to traffic/CVR/rating/ads/price (Chinese).
6. Product Dev VOC — mine competitor reviews for unmet needs and improvements (Chinese).
7. Data Upload — import Seller Central / Advertising CSVs to overlay real operational data.

This UI talks to the FastAPI backend over HTTP so that the web frontend and the
API can be deployed as separate containers.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

st.set_page_config(page_title="PawPilot", page_icon="🐾", layout="wide")

API_BASE_URL = os.environ.get("PAWPILOT_API_URL", "http://localhost:8000")

st.title("🐾 PawPilot — Amazon Pet-Supplies Operations Copilot")
st.markdown("RAG knowledge base + Agent workflows for cross-border e-commerce operations.")

# Sidebar: provider selection and scenario notes.
with st.sidebar:
    st.header("Settings")
    provider = st.selectbox("LLM provider", ["deepseek", "qwen"], index=0)
    st.markdown("---")
    st.markdown("**Scenarios**")
    st.markdown("- Policy Q&A")
    st.markdown("- Listing Generator")
    st.markdown("- Review Analysis")
    st.markdown("- Ops Daily Digest")
    st.markdown("- Sales Diagnosis")
    st.markdown("- Product Dev VOC")
    st.markdown("- Data Upload")


tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [
        "Policy Q&A",
        "Listing Generator",
        "Review Analysis",
        "Ops Daily Digest",
        "Sales Diagnosis",
        "Product Dev VOC",
        "Data Upload",
    ]
)


def _call_api(method: str, path: str, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the FastAPI backend synchronously.

    Returns a normal response dict on success, or an error dict with
    `_api_error=True` and `detail` when the backend is unreachable. Callers
    should check for `_api_error` before accessing result fields.
    """
    url = f"{API_BASE_URL}{path}"
    headers = {"X-Provider": provider}

    try:
        with httpx.Client(timeout=120.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            else:
                response = client.post(url, json=json_payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        # Backend is not running — surface a friendly message instead of a traceback.
        error_detail = (
            f"Cannot connect to PawPilot API at {url}. "
            "Please make sure the FastAPI backend is running:\n\n"
            "uv run uvicorn app.api.main:app --reload"
        )
        return {"_api_error": True, "detail": error_detail}


def _call_upload_api(path: str, file: Any, filename: str, form: dict[str, str]) -> dict[str, Any]:
    """Upload a CSV file to the FastAPI backend."""
    url = f"{API_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                url,
                files={"file": (filename, file, "text/csv")},
                data=form,
            )
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        return {
            "_api_error": True,
            "detail": (
                f"Cannot connect to PawPilot API at {url}. "
                "Please make sure the FastAPI backend is running."
            ),
        }


with tab1:
    st.header("Amazon Policy & SOP Q&A")
    query = st.text_input(
        "Ask a question",
        value="What is the maximum title length for Pet Supplies listings?",
        key="policy_query",
    )
    if st.button("Ask", key="ask_btn"):
        with st.spinner("Retrieving and generating answer..."):
            result = _call_api("POST", "/api/ask", {"query": query})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown("### Answer")
            st.markdown(result["answer"])
            with st.expander("Sources"):
                for src in result.get("sources", []):
                    st.markdown(f"**{src.get('doc_id')}** — {src.get('section')}")
                    st.markdown(f"```{src.get('text')[:400]}...```")
            with st.expander("Usage"):
                st.json(result.get("usage", {}))


with tab2:
    st.header("Listing Generator + Compliance Check")
    product_info = {
        "sku": st.text_input("SKU", value="PP-RT-102", key="sku"),
        "product_type": st.text_input("Product type", value="cotton rope dog toy"),
        "target_dog_weight": st.text_input("Target dog weight", value="15-30 kg"),
        "size": st.text_input("Size", value="Medium, 30 cm"),
        "color": st.text_input("Color", value="Natural white + green"),
        "material": st.text_input("Material", value="100% natural cotton, AZO-free dye"),
        "key_feature": st.text_input("Key feature", value="designed for aggressive chewers"),
        "packaging": st.text_input("Packaging", value="PE bag + hang tag"),
    }
    if st.button("Generate listing", key="gen_btn"):
        with st.spinner("Generating and reviewing listing..."):
            result = _call_api("POST", "/api/listing", {"product_info": product_info})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown("### Result")
            st.markdown(result["final_answer"])
            with st.expander("Tool calls"):
                st.json(result.get("tool_calls", []))


with tab3:
    st.header("Review Analysis")
    sku_input = st.selectbox("SKU", ["PP-RT-101", "PP-RT-102", "PP-RT-103", "PP-HR-201", "PP-HR-203", "PP-SB-302"], index=4, key="review_sku")
    days_input = st.slider("Days", min_value=7, max_value=365, value=90, key="review_days")
    if st.button("Analyze", key="review_btn"):
        with st.spinner("Analyzing reviews..."):
            result = _call_api("POST", "/api/reviews", {"sku": sku_input, "days": days_input})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown("### Analysis")
            st.markdown(result["final_answer"])
            with st.expander("Tool calls"):
                st.json(result.get("tool_calls", []))


with tab4:
    st.header("Ops Daily Digest")
    st.markdown("Portfolio-level daily briefing: sales WoW, margin, inventory cover, ACOS, and rating alerts.")
    if st.button("Generate digest", key="digest_btn"):
        with st.spinner("Generating daily digest..."):
            result = _call_api("POST", "/api/digest")
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown("### Daily Digest")
            st.markdown(result["final_answer"])
            with st.expander("Tool calls"):
                st.json(result.get("tool_calls", []))


with tab5:
    st.header("Sales Diagnosis")
    diagnose_sku = st.selectbox("SKU", ["PP-RT-101", "PP-RT-102", "PP-RT-103", "PP-HR-201", "PP-HR-203", "PP-SB-302"], index=1, key="diagnose_sku")
    diagnose_days = st.slider("Days", min_value=7, max_value=60, value=14, key="diagnose_days")
    if st.button("Diagnose", key="diagnose_btn"):
        with st.spinner("Diagnosing sales anomaly..."):
            result = _call_api("POST", "/api/diagnose", {"sku": diagnose_sku, "days": diagnose_days})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown("### Diagnosis")
            st.markdown(result["final_answer"])
            with st.expander("Tool calls"):
                st.json(result.get("tool_calls", []))


with tab6:
    st.header("Product Dev VOC")
    product_type = st.selectbox("Product type", ["rope toy", "harness", "feeder bowl"], index=0, key="product_type")
    if st.button("Analyze VOC", key="voc_btn"):
        with st.spinner("Mining competitor reviews for product opportunities..."):
            result = _call_api("POST", "/api/product-dev", {"product_type": product_type})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown("### Product Development Report")
            st.markdown(result["final_answer"])
            with st.expander("Tool calls"):
                st.json(result.get("tool_calls", []))


with tab7:
    st.header("Data Upload — Seller Central / Advertising CSV")
    st.markdown(
        "上传亚马逊后台导出的 CSV，自动识别报表类型并覆盖到运营数据层。"
        "支持 Business Report（销量）、Advertising Report（广告）、FBA Inventory Report（库存）、"
        "SKU 成本表（利润）。导入后，诊断 / 日报 / 库存 / 利润工具会优先使用真实数据。"
    )

    col1, col2 = st.columns(2)
    with col1:
        account_id = st.text_input("Account ID（店铺/账号）", value="default", key="upload_account")
    with col2:
        marketplace = st.selectbox("Marketplace", ["US", "UK", "DE", "JP", "CA"], key="upload_marketplace")

    uploaded_files = st.file_uploader(
        "选择 CSV 文件（可多选）",
        type=["csv"],
        accept_multiple_files=True,
        key="csv_uploader",
    )

    if st.button("导入数据", key="csv_import_btn"):
        if not uploaded_files:
            st.warning("请先选择 CSV 文件。")
        else:
            for uploaded in uploaded_files:
                with st.spinner(f"Importing {uploaded.name}..."):
                    result = _call_upload_api(
                        "/api/import-csv",
                        file=uploaded.getvalue(),
                        filename=uploaded.name,
                        form={"account_id": account_id, "marketplace": marketplace},
                    )
                if result.get("_api_error"):
                    st.error(result["detail"])
                    continue
                st.success(
                    f"**{uploaded.name}** — {result['rows_imported']} 行导入成功 "
                    f"（检测类型：{result['csv_type']}，置信度：{result['detection']['confidence']}）"
                )
                if result.get("warnings"):
                    st.warning("\n".join(result["warnings"]))
                with st.expander(f"列映射详情 — {uploaded.name}"):
                    st.write("匹配列：", result["detection"]["matched_columns"])
                    if result["detection"]["missing_columns"]:
                        st.write("缺失列（已使用默认值）：", result["detection"]["missing_columns"])

    with st.expander("支持的 CSV 类型"):
        types_result = _call_api("GET", "/api/import-csv/types")
        if types_result.get("_api_error"):
            st.error(types_result["detail"])
        else:
            for t in types_result["types"]:
                st.markdown(f"**{t['name']}** (`{t['type']}`)")
                st.markdown(f"- 必需列：{', '.join(t['required_columns'])}")
                st.markdown(f"- 可识别表头：{', '.join(t['recognisable_headers'])}")
