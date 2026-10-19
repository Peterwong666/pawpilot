"""HTTP client helpers for the PawPilot FastAPI backend.

Centralises every backend call used by the Streamlit UI: scenario POSTs,
cached list fetches (SKUs / product types / accounts / history / stats),
CSV uploads and the metrics endpoints behind the dashboard tab.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

from web.i18n import t

API_BASE_URL = os.environ.get("PAWPILOT_API_URL", "http://localhost:8000")

SCENARIO_LABELS = {
    "review_analysis": "评论分析",
    "ops_digest": "运营日报",
    "sales_diagnosis": "销量诊断",
    "product_dev": "产品开发VOC",
}


def http_error_detail(exc: httpx.HTTPStatusError) -> str:
    """Build a readable message from a non-2xx response."""
    detail = exc.response.text
    try:
        detail = exc.response.json().get("detail", detail)
    except ValueError:
        pass
    return t("err.http_error", code=exc.response.status_code, detail=detail)


def call_api(method: str, path: str, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the FastAPI backend synchronously with provider + account context headers."""
    url = f"{API_BASE_URL}{path}"
    provider = st.session_state.get("provider", "deepseek")
    account_id = st.session_state.get("selected_account", "default")
    marketplace = st.session_state.get("selected_marketplace", "US")
    use_simulated = st.session_state.get("use_simulated", True)
    headers = {
        "X-Provider": provider,
        "X-Account-Id": account_id,
        "X-Marketplace": marketplace,
        "X-Use-Simulated": "false" if not use_simulated else "true",
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers, params=json_payload)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers, params=json_payload)
            else:
                response = client.post(url, json=json_payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        return {"_api_error": True, "detail": t("err.backend_down", url=url)}
    except httpx.HTTPStatusError as exc:
        # Never let a non-2xx (e.g. a 404 from an older API during the
        # tab7 /types probe) crash the whole Streamlit rerun; surface it
        # as an in-page error in the tab that made the call.
        return {"_api_error": True, "detail": http_error_detail(exc)}


def call_upload_api(path: str, file: Any, filename: str, form: dict[str, str]) -> dict[str, Any]:
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
        return {"_api_error": True, "detail": t("err.backend_down_short", url=url)}
    except httpx.HTTPStatusError as exc:
        return {"_api_error": True, "detail": http_error_detail(exc)}


def invalidate_data_caches() -> None:
    """Clear cached SKU / product-type / account lists after data imports or deletes."""
    for key in ("_sku_cache", "_product_type_cache", "_account_cache"):
        st.session_state.pop(key, None)


def save_history(
    scenario: str, input_data: dict[str, Any], output_data: dict[str, Any], summary: str = ""
) -> None:
    """Save an analysis result to the backend history store (best-effort)."""
    try:
        call_api("POST", "/api/history", {
            "scenario": scenario,
            "input_data": input_data,
            "output_data": output_data,
            "summary": summary,
        })
        # Invalidate the history cache so the sidebar list refreshes automatically.
        st.session_state.pop("_history_cache", None)
    except Exception:
        pass


def fetch_history() -> list[dict[str, Any]]:
    """Fetch recent analysis history for the active account."""
    cached = st.session_state.get("_history_cache")
    if cached is not None:
        return cached
    result = call_api("GET", "/api/history")
    records = result.get("history", []) if not result.get("_api_error") else []
    st.session_state["_history_cache"] = records
    return records


def fetch_stats() -> dict[str, Any]:
    """Fetch aggregated request stats from the backend (/stats, added in P4)."""
    result = call_api("GET", "/stats")
    return {} if result.get("_api_error") else result


def fetch_skus() -> list[str]:
    """Fetch the list of available SKUs from the backend (cached per session)."""
    cached = st.session_state.get("_sku_cache")
    if cached is not None:
        return cached
    result = call_api("GET", "/api/skus")
    skus = result.get("skus", []) if not result.get("_api_error") else []
    st.session_state["_sku_cache"] = skus
    return skus


def fetch_product_types() -> list[str]:
    """Fetch the list of available product types from the backend (cached per session)."""
    cached = st.session_state.get("_product_type_cache")
    if cached is not None:
        return cached
    result = call_api("GET", "/api/product-types")
    types = result.get("product_types", []) if not result.get("_api_error") else []
    st.session_state["_product_type_cache"] = types
    return types


def fetch_accounts() -> list[dict[str, str]]:
    """Fetch the list of (account_id, marketplace) pairs that have imported data."""
    cached = st.session_state.get("_account_cache")
    if cached is not None:
        return cached
    result = call_api("GET", "/api/accounts")
    accounts = result.get("accounts", []) if not result.get("_api_error") else []
    st.session_state["_account_cache"] = accounts
    return accounts
