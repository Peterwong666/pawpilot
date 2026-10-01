"""Streamlit demo UI for PawPilot.

Three scenario tabs:
1. Policy Q&A — ask Amazon policy questions.
2. Listing Generator — generate and review a listing from product info.
3. Review Analysis — analyze simulated reviews for a SKU.

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


tab1, tab2, tab3 = st.tabs(["Policy Q&A", "Listing Generator", "Review Analysis"])


def _call_api(method: str, path: str, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the FastAPI backend synchronously."""
    url = f"{API_BASE_URL}{path}"
    headers = {"X-Provider": provider}
    with httpx.Client(timeout=120.0) as client:
        if method.upper() == "GET":
            response = client.get(url, headers=headers)
        else:
            response = client.post(url, json=json_payload, headers=headers)
    response.raise_for_status()
    return response.json()


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
        st.markdown("### Result")
        st.markdown(result["final_answer"])
        with st.expander("Tool calls"):
            st.json(result.get("tool_calls", []))


with tab3:
    st.header("Review Analysis")
    sku_input = st.text_input("SKU", value="PP-HR-203", key="review_sku")
    days_input = st.slider("Days", min_value=7, max_value=365, value=90)
    if st.button("Analyze", key="review_btn"):
        with st.spinner("Analyzing reviews..."):
            result = _call_api("POST", "/api/reviews", {"sku": sku_input, "days": days_input})
        st.markdown("### Analysis")
        st.markdown(result["final_answer"])
        with st.expander("Tool calls"):
            st.json(result.get("tool_calls", []))
