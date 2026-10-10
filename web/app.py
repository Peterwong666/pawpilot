"""Streamlit demo UI for PawPilot.

Seven scenario tabs:
1. Policy Q&A — ask Amazon policy questions.
2. Listing Generator — generate and review a listing from product info.
3. Review Analysis — analyze reviews for a SKU.
4. Ops Daily Digest — portfolio-level daily operations briefing.
5. Sales Diagnosis — attribute a SKU's sales change to traffic/CVR/rating/ads/price.
6. Product Dev VOC — mine competitor reviews for unmet needs and improvements.
7. Data Upload — import Seller Central / Advertising CSVs.

All user-visible strings go through ``t(key)`` so the UI can switch between
Chinese (default) and English via the sidebar selector.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd
import streamlit as st

from web.i18n import DEFAULT_LANG, init_lang, t

# init_lang seeds st.session_state.lang = "zh" if absent. We run it BEFORE
# set_page_config so menu_items can resolve t() with the current language
# on every rerun (Streamlit 1.64 accepts additive set_page_config calls).
init_lang()

# set_page_config runs every rerun so its menu_items follow language switch.
# Keys: "about" accepts markdown text; "get help" / "report a bug" need URLs.
st.set_page_config(
    page_title="PawPilot",
    page_icon="🐾",
    layout="wide",
    menu_items={
        "about": t("menu.about"),
        "get help": "https://github.com/Peterwong666/pawpilot",
        "report a bug": "https://github.com/Peterwong666/pawpilot/issues",
    },
)

# Streamlit ships an unlocalised "Deploy" promo button in the header. It
# is irrelevant for local development and its popup contains hard-coded
# English strings we cannot reach from Python. The canonical workaround
# used across the Streamlit community is to hide it via CSS. The
# [data-testid="stToolbar"] parent guards the selector so only the
# *header* button disappears; a footer deploy button (if any) is left
# alone. The [role="dialog"] rule also masks the popup backdrop.
st.markdown(
    """
    <style>
    [data-testid="stToolbar"] [data-testid="stBaseButton-header"] {
        display: none !important;
    }
    [role="dialog"][aria-label*="Deploy" i] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

API_BASE_URL = os.environ.get("PAWPILOT_API_URL", "http://localhost:8000")

_SCENARIO_LABELS = {
    "review_analysis": "评论分析",
    "ops_digest": "运营日报",
    "sales_diagnosis": "销量诊断",
    "product_dev": "产品开发VOC",
}

st.title(t("app.title"))
st.markdown(t("app.subtitle"))

# ---- New user onboarding (first visit only) ----
if not st.session_state.get("onboarding_done"):
    with st.container(border=True):
        st.markdown(f"### 👋 {t('onboarding.title')}")
        st.markdown(t("onboarding.intro"))
        st.markdown(t("onboarding.steps"))
        col_a, col_b = st.columns([1, 4])
        with col_a:
            if st.button(t("onboarding.got_it"), key="onboarding_gotit"):
                st.session_state["onboarding_done"] = True
                st.rerun()
        with col_b:
            if st.button(t("onboarding.dont_show"), key="onboarding_skip"):
                st.session_state["onboarding_done"] = True
                st.rerun()
    st.markdown("---")

# ---- History viewer (shown when a history record is selected) ----
_hist_view = st.session_state.get("_history_view")
if _hist_view:
    with st.container(border=True):
        label = _SCENARIO_LABELS.get(_hist_view.get("scenario", ""), _hist_view.get("scenario", ""))
        st.markdown(f"### 📋 {t('sidebar.history')} — {label}")
        st.caption(f"{_hist_view.get('created_at', '')}")
        output = _hist_view.get("output_data", {})
        if output.get("final_answer"):
            st.markdown(output["final_answer"])
        else:
            st.json(output)
        col_close, col_download = st.columns([1, 1])
        with col_close:
            if st.button(t("sidebar.history_close"), key="hist_close"):
                st.session_state.pop("_history_view", None)
                st.rerun()
        with col_download:
            if output.get("final_answer"):
                st.download_button(
                    t("t5.btn_export"),
                    data=output["final_answer"],
                    file_name=f"history_{_hist_view.get('scenario','analysis')}_{_hist_view.get('id','')}.md",
                    mime="text/markdown",
                    key="hist_download",
                )
    st.markdown("---")

# Sidebar: language, provider, scenario list.
with st.sidebar:
    st.header(t("sidebar.settings"))
    st.selectbox(
        t("sidebar.lang"),
        ["zh", "en"],
        index=0 if st.session_state.get("lang", DEFAULT_LANG) == "zh" else 1,
        key="lang",
        format_func=lambda x: t("sidebar.lang_option_zh") if x == "zh" else t("sidebar.lang_option_en"),
    )
    provider = st.selectbox("LLM provider", ["deepseek", "qwen"], index=0, key="provider")

    st.markdown("---")
    st.markdown(f"**{t('sidebar.scenarios')}**")
    st.markdown(f"- {t('sidebar.scen_policy')}")
    st.markdown(f"- {t('sidebar.scen_listing')}")
    st.markdown(f"- {t('sidebar.scen_reviews')}")
    st.markdown(f"- {t('sidebar.scen_digest')}")
    st.markdown(f"- {t('sidebar.scen_diagnose')}")
    st.markdown(f"- {t('sidebar.scen_voc')}")
    st.markdown(f"- {t('sidebar.scen_upload')}")


tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    [
        t("tab.policy"),
        t("tab.listing"),
        t("tab.reviews"),
        t("tab.digest"),
        t("tab.diagnose"),
        t("tab.voc"),
        t("tab.upload"),
        t("tab.data_mgmt"),
    ]
)


def _call_api(method: str, path: str, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
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
        return {"_api_error": True, "detail": _http_error_detail(exc)}


def _invalidate_data_caches() -> None:
    """Clear cached SKU / product-type / account lists after data imports or deletes."""
    for key in ("_sku_cache", "_product_type_cache", "_account_cache"):
        st.session_state.pop(key, None)


def _save_history(scenario: str, input_data: dict[str, Any], output_data: dict[str, Any], summary: str = "") -> None:
    """Save an analysis result to the backend history store (best-effort)."""
    try:
        _call_api("POST", "/api/history", {
            "scenario": scenario,
            "input_data": input_data,
            "output_data": output_data,
            "summary": summary,
        })
        # Invalidate the history cache so the sidebar list refreshes automatically.
        st.session_state.pop("_history_cache", None)
    except Exception:
        pass


def _fetch_history() -> list[dict[str, Any]]:
    """Fetch recent analysis history for the active account."""
    cached = st.session_state.get("_history_cache")
    if cached is not None:
        return cached
    result = _call_api("GET", "/api/history")
    records = result.get("history", []) if not result.get("_api_error") else []
    st.session_state["_history_cache"] = records
    return records


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
        return {"_api_error": True, "detail": t("err.backend_down_short", url=url)}
    except httpx.HTTPStatusError as exc:
        return {"_api_error": True, "detail": _http_error_detail(exc)}


def _http_error_detail(exc: httpx.HTTPStatusError) -> str:
    """Build a readable message from a non-2xx response."""
    detail = exc.response.text
    try:
        detail = exc.response.json().get("detail", detail)
    except ValueError:
        pass
    return t("err.http_error", code=exc.response.status_code, detail=detail)


def _fetch_skus() -> list[str]:
    """Fetch the list of available SKUs from the backend (cached per session)."""
    cached = st.session_state.get("_sku_cache")
    if cached is not None:
        return cached
    result = _call_api("GET", "/api/skus")
    skus = result.get("skus", []) if not result.get("_api_error") else []
    st.session_state["_sku_cache"] = skus
    return skus


def _fetch_product_types() -> list[str]:
    """Fetch the list of available product types from the backend (cached per session)."""
    cached = st.session_state.get("_product_type_cache")
    if cached is not None:
        return cached
    result = _call_api("GET", "/api/product-types")
    types = result.get("product_types", []) if not result.get("_api_error") else []
    st.session_state["_product_type_cache"] = types
    return types


def _fetch_accounts() -> list[dict[str, str]]:
    """Fetch the list of (account_id, marketplace) pairs that have imported data."""
    cached = st.session_state.get("_account_cache")
    if cached is not None:
        return cached
    result = _call_api("GET", "/api/accounts")
    accounts = result.get("accounts", []) if not result.get("_api_error") else []
    st.session_state["_account_cache"] = accounts
    return accounts


# Sidebar: data context (account / marketplace / simulated data toggle).
# Placed here after helper functions are defined.
with st.sidebar:
    st.markdown("---")
    st.subheader(t("sidebar.data_context"))

    accounts = _fetch_accounts()
    account_ids = sorted({a["account_id"] for a in accounts}) if accounts else ["default"]
    account_id = st.selectbox(
        t("sidebar.account"),
        account_ids,
        index=0,
        key="selected_account",
        help=t("sidebar.account_help"),
    )
    marketplace = st.selectbox(
        t("sidebar.marketplace"),
        ["US", "UK", "DE", "JP", "CA", "AU"],
        index=0,
        key="selected_marketplace",
        help=t("sidebar.marketplace_help"),
    )
    use_simulated = st.toggle(
        t("sidebar.use_simulated"),
        value=True,
        key="use_simulated",
        help=t("sidebar.use_simulated_help"),
    )

    # Invalidate SKU / product-type caches when the data context changes.
    ctx_key = (account_id, marketplace, use_simulated)
    if st.session_state.get("_data_context_key") != ctx_key:
        st.session_state.pop("skus", None)
        st.session_state.pop("product_types", None)
        st.session_state["_data_context_key"] = ctx_key

    # ---- History panel ----
    st.markdown("---")
    with st.expander(t("sidebar.history"), expanded=False):
        if st.button(t("sidebar.history_refresh"), key="history_refresh"):
            st.session_state.pop("_history_cache", None)
            st.rerun()
        records = _fetch_history()
        if not records:
            st.caption(t("sidebar.history_empty"))
        else:
            for rec in records[:20]:
                label = _SCENARIO_LABELS.get(rec.get("scenario", ""), rec.get("scenario", ""))
                ts = (rec.get("created_at") or "")[:16].replace("T", " ")
                summary = rec.get("summary") or ""
                if summary:
                    summary = summary[:40] + ("…" if len(summary) > 40 else "")
                if st.button(f"📋 {label} — {ts}", key=f"hist_{rec['id']}"):
                    st.session_state["_history_view"] = rec
                    st.rerun()


with tab1:
    st.header(t("t1.header"))
    if "policy_chat" not in st.session_state:
        st.session_state.policy_chat = []

    # Render conversation history.
    for msg in st.session_state.policy_chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander(t("t1.sources")):
                    for src in msg["sources"]:
                        st.markdown(f"**{src.get('doc_id')}** — {src.get('section')}")
                        st.markdown(f"```{src.get('text', '')[:400]}...```")

    query = st.chat_input(t("t1.query_label"))
    if query:
        st.session_state.policy_chat.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)
        with st.spinner(t("t1.spinner")):
            result = _call_api("POST", "/api/ask", {"query": query})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            with st.chat_message("assistant"):
                st.markdown(answer)
                if sources:
                    with st.expander(t("t1.sources")):
                        for src in sources:
                            st.markdown(f"**{src.get('doc_id')}** — {src.get('section')}")
                            st.markdown(f"```{src.get('text', '')[:400]}...```")
            st.session_state.policy_chat.append({
                "role": "assistant",
                "content": answer,
                "sources": sources,
            })

    if st.session_state.policy_chat and st.button(t("t1.clear_chat"), key="clear_chat_btn"):
        st.session_state.policy_chat = []
        st.rerun()


with tab2:
    st.header(t("t2.header"))
    product_info = {
        "sku": st.text_input(t("t2.l_sku"), value="PP-RT-102", key="sku"),
        "product_type": st.text_input(t("t2.l_product_type"), value="cotton rope dog toy"),
        "target_dog_weight": st.text_input(t("t2.l_dog_weight"), value="15-30 kg"),
        "size": st.text_input(t("t2.l_size"), value="Medium, 30 cm"),
        "color": st.text_input(t("t2.l_color"), value="Natural white + green"),
        "material": st.text_input(t("t2.l_material"), value="100% natural cotton, AZO-free dye"),
        "key_feature": st.text_input(t("t2.l_key_feature"), value="designed for aggressive chewers"),
        "packaging": st.text_input(t("t2.l_packaging"), value="PE bag + hang tag"),
    }

    # ---- Custom attributes (dynamic) ----
    if "custom_attrs" not in st.session_state:
        st.session_state.custom_attrs = []

    st.markdown(f"**{t('t2.custom_title')}**")
    cols_attr = st.columns([3, 3, 1])
    with cols_attr[0]:
        new_attr_name = st.text_input(t("t2.custom_name"), key="new_attr_name", label_visibility="collapsed", placeholder=t("t2.custom_name_ph"))
    with cols_attr[1]:
        new_attr_val = st.text_input(t("t2.custom_value"), key="new_attr_val", label_visibility="collapsed", placeholder=t("t2.custom_value_ph"))
    with cols_attr[2]:
        if st.button(t("t2.custom_add"), key="add_attr_btn"):
            if new_attr_name.strip():
                st.session_state.custom_attrs.append({"name": new_attr_name.strip(), "value": new_attr_val.strip()})
                st.session_state.new_attr_name = ""
                st.session_state.new_attr_val = ""
                st.rerun()

    # Render existing custom attributes (editable) with delete buttons.
    if st.session_state.custom_attrs:
        for i, attr in enumerate(st.session_state.custom_attrs):
            c1, c2, c3 = st.columns([3, 3, 1])
            with c1:
                st.text_input(t("t2.custom_name"), value=attr["name"], key=f"attr_name_{i}", label_visibility="collapsed")
            with c2:
                st.text_input(t("t2.custom_value"), value=attr["value"], key=f"attr_val_{i}", label_visibility="collapsed")
            with c3:
                if st.button("🗑", key=f"del_attr_{i}"):
                    st.session_state.custom_attrs.pop(i)
                    st.rerun()
        # Sync editable inputs back into custom_attrs.
        for i, attr in enumerate(st.session_state.custom_attrs):
            name_val = st.session_state.get(f"attr_name_{i}", attr["name"])
            val_val = st.session_state.get(f"attr_val_{i}", attr["value"])
            attr["name"] = name_val
            attr["value"] = val_val
        # Merge custom attrs into product_info.
        for attr in st.session_state.custom_attrs:
            if attr["name"]:
                product_info[attr["name"]] = attr["value"]

    if st.button(t("t2.btn_gen"), key="gen_btn"):
        with st.spinner(t("t2.spinner")):
            result = _call_api("POST", "/api/listing", {"product_info": product_info})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown(f"### {t('t2.result')}")
            st.markdown(result["final_answer"])
            with st.expander(t("t2.tool_calls")):
                st.json(result.get("tool_calls", []))


with tab3:
    st.header(t("t3.header"))
    sku_options = _fetch_skus()
    sku_input = st.multiselect(
        t("t3.l_sku"),
        options=sku_options,
        default=[sku_options[4]] if len(sku_options) > 4 else sku_options[:1],
        key="review_sku",
        help=t("t3.l_sku_help"),
    )
    days_input = st.slider(t("t3.l_days"), min_value=7, max_value=365, value=90, key="review_days")
    if st.button(t("t3.btn_analyze"), key="review_btn"):
        if not sku_input:
            st.warning(t("t3.warn_no_sku"))
        else:
            with st.spinner(t("t3.spinner")):
                result = _call_api("POST", "/api/reviews", {"sku": sku_input, "days": days_input})
            if result.get("_api_error"):
                st.error(result["detail"])
            else:
                st.markdown(f"### {t('t3.analysis')}")
                st.markdown(result["final_answer"])
                st.download_button(
                    t("t3.btn_export"),
                    data=result["final_answer"],
                    file_name=f"review_analysis_{'_'.join(sku_input)}_{days_input}d.md",
                    mime="text/markdown",
                    key="review_export",
                )
                _save_history(
                    "review_analysis",
                    {"sku": sku_input, "days": days_input},
                    {"final_answer": result.get("final_answer", "")},
                    summary=f"SKU: {', '.join(sku_input)}",
                )
                with st.expander(t("t2.tool_calls")):
                    st.json(result.get("tool_calls", []))


with tab4:
    st.header(t("t4.header"))
    st.markdown(t("t4.desc"))
    if st.button(t("t4.btn_digest"), key="digest_btn"):
        with st.spinner(t("t4.spinner")):
            result = _call_api("POST", "/api/digest")
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            digest = result.get("digest", {})
            sku_rows = digest.get("sku_rows", [])
            alerts = digest.get("alerts", [])
            acos_target = digest.get("acos_target_pct", 30.0)

            # ---- Metric cards ----
            if sku_rows:
                total_units = sum(r.get("units_7d", 0) for r in sku_rows)
                total_revenue = sum(r.get("revenue_7d", 0) for r in sku_rows)
                total_profit = sum(r.get("est_profit_7d", 0) for r in sku_rows)
                low_stock = sum(1 for r in sku_rows if r.get("inventory_status") in ("low", "out"))
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(t("t4.m_total_units"), f"{total_units:,.0f}")
                c2.metric(t("t4.m_total_revenue"), f"${total_revenue:,.2f}")
                c3.metric(t("t4.m_total_profit"), f"${total_profit:,.2f}")
                c4.metric(t("t4.m_alerts"), f"{len(alerts)}", delta=f"{digest.get('alert_count', len(alerts))}")

                # ---- Charts ----
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    st.markdown(f"**{t('t4.chart_units')}**")
                    units_df = pd.DataFrame([
                        {"SKU": r["sku"], t("t4.m_units_7d"): r.get("units_7d", 0)}
                        for r in sku_rows
                    ])
                    st.bar_chart(units_df.set_index("SKU"), use_container_width=True)
                with col_chart2:
                    st.markdown(f"**{t('t4.chart_acos')}** (target={acos_target}%)")
                    acos_df = pd.DataFrame([
                        {"SKU": r["sku"], "ACOS%": r.get("acos_7d", 0)}
                        for r in sku_rows
                    ])
                    st.bar_chart(acos_df.set_index("SKU"), use_container_width=True)

                # ---- SKU table with inventory highlighting ----
                st.markdown(f"**{t('t4.table_title')}**")
                table_rows = []
                for r in sku_rows:
                    inv = r.get("inventory_status", "ok")
                    inv_label = {"ok": "✓", "low": "⚠", "out": "✕"}.get(inv, inv)
                    table_rows.append({
                        "SKU": r["sku"],
                        t("t4.col_units"): r.get("units_7d", 0),
                        t("t4.col_wow"): f"{r.get('units_wow_pct', 0):+.1f}%",
                        t("t4.col_revenue"): f"${r.get('revenue_7d', 0):,.2f}",
                        t("t4.col_margin"): f"{r.get('margin_pct', 0):.1f}%",
                        t("t4.col_acos"): f"{r.get('acos_7d', 0):.1f}%",
                        t("t4.col_rating"): f"{r.get('rating_7d', 0):.2f}",
                        t("t4.col_inv"): f"{inv_label} {r.get('days_of_cover', 0)}d",
                    })
                if table_rows:
                    df = pd.DataFrame(table_rows)
                    # Highlight low/out-of-stock rows
                    def _highlight_inv(row):
                        inv_cell = str(row.get(t("t4.col_inv"), ""))
                        if inv_cell.startswith("✕"):
                            return ["background-color: #ffe0e0"] * len(row)
                        if inv_cell.startswith("⚠"):
                            return ["background-color: #fff8e0"] * len(row)
                        return [""] * len(row)
                    st.dataframe(df.style.apply(_highlight_inv, axis=1), use_container_width=True, hide_index=True)

                # ---- Alerts ----
                if alerts:
                    st.markdown(f"**{t('t4.alerts_title')}** ({len(alerts)})")
                    for a in alerts:
                        sev = a.get("severity", "info")
                        icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "🔵")
                        with st.container():
                            st.markdown(
                                f"{icon} **[{a.get('sku','-')}] {a.get('type','')}** — {a.get('detail','')}"
                            )
                            if a.get("action"):
                                st.caption(f"→ {a['action']}")
            else:
                st.info(t("t4.no_data"))

            st.markdown(f"### {t('t4.digest_title')}")
            st.markdown(result["final_answer"])
            st.download_button(
                t("t4.btn_export"),
                data=result["final_answer"],
                file_name="ops_daily_digest.md",
                mime="text/markdown",
                key="digest_export",
            )
            _save_history(
                "ops_digest",
                {},
                {"final_answer": result.get("final_answer", ""), "digest": digest},
                summary=f"{len(alerts)} alerts",
            )
            with st.expander(t("t2.tool_calls")):
                st.json(result.get("tool_calls", []))


with tab5:
    st.header(t("t5.header"))
    sku_options = _fetch_skus()
    diagnose_sku = st.multiselect(
        t("t5.l_sku"),
        options=sku_options,
        default=[sku_options[1]] if len(sku_options) > 1 else sku_options[:1],
        key="diagnose_sku",
        help=t("t5.l_sku_help"),
    )
    diagnose_days = st.slider(t("t5.l_days"), min_value=7, max_value=60, value=14, key="diagnose_days")
    if st.button(t("t5.btn_diagnose"), key="diagnose_btn"):
        if not diagnose_sku:
            st.warning(t("t5.warn_no_sku"))
        else:
            with st.spinner(t("t5.spinner")):
                result = _call_api("POST", "/api/diagnose", {"sku": diagnose_sku, "days": diagnose_days})
            if result.get("_api_error"):
                st.error(result["detail"])
            else:
                # Visualization: metrics comparison for each diagnosed SKU.
                diagnoses = result.get("diagnoses") or ([result["diagnosis"]] if result.get("diagnosis") else [])
                for diag in diagnoses:
                    sku = diag.get("sku", "")
                    metrics = diag.get("metrics", {})
                    cur = metrics.get("current", {})
                    prev = metrics.get("previous", {})
                    if not cur or not prev:
                        continue
                    st.markdown(f"#### 📊 {sku} 指标对比")
                    metric_labels = {
                        "units": t("t5.m_units"),
                        "sessions": t("t5.m_sessions"),
                        "cvr": t("t5.m_cvr"),
                        "price": t("t5.m_price"),
                        "ad_spend": t("t5.m_ad_spend"),
                        "avg_rating": t("t5.m_rating"),
                    }
                    rows = []
                    for key, label in metric_labels.items():
                        if key in cur and key in prev:
                            rows.append({"指标": label, "本期": cur[key], "上期": prev[key]})
                    if rows:
                        comp_df = pd.DataFrame(rows)
                        st.dataframe(comp_df, use_container_width=True, hide_index=True)
                        # Grouped bar chart: current vs previous.
                        try:
                            chart_df = comp_df.set_index("指标")
                            st.bar_chart(chart_df, use_container_width=True)
                        except Exception:
                            pass
                st.markdown(f"### {t('t5.diagnosis')}")
                st.markdown(result["final_answer"])
                st.download_button(
                    t("t5.btn_export"),
                    data=result["final_answer"],
                    file_name=f"diagnosis_{'_'.join(diagnose_sku)}_{diagnose_days}d.md",
                    mime="text/markdown",
                    key="diagnose_export",
                )
                _save_history(
                    "sales_diagnosis",
                    {"sku": diagnose_sku, "days": diagnose_days},
                    {"final_answer": result.get("final_answer", "")},
                    summary=f"SKU: {', '.join(diagnose_sku)}",
                )
                with st.expander(t("t2.tool_calls")):
                    st.json(result.get("tool_calls", []))


with tab6:
    st.header(t("t6.header"))
    # Options are canonical English keys fetched from the backend (competitor_reviews table);
    # format_func renders the localized label so the payload stays valid regardless of UI language.
    pt_options = _fetch_product_types()
    _PT_LABELS = {
        "rope toy": t("t6.opt_rope"),
        "harness": t("t6.opt_harness"),
        "feeder bowl": t("t6.opt_feeder"),
    }
    product_types = st.multiselect(
        t("t6.l_product_type"),
        options=pt_options,
        default=[pt_options[0]] if pt_options else [],
        key="product_type",
        format_func=lambda x: _PT_LABELS.get(x, x),
        help=t("t6.l_product_type_help"),
    )
    if st.button(t("t6.btn_voc"), key="voc_btn"):
        if not product_types:
            st.warning(t("t6.warn_no_product_type"))
        else:
            with st.spinner(t("t6.spinner")):
                result = _call_api("POST", "/api/product-dev", {"product_type": product_types})
            if result.get("_api_error"):
                st.error(result["detail"])
            else:
                st.markdown(f"### {t('t6.report')}")
                st.markdown(result["final_answer"])
                st.download_button(
                    t("t6.btn_export"),
                    data=result["final_answer"],
                    file_name=f"product_dev_{'_'.join(product_types)}.md",
                    mime="text/markdown",
                    key="voc_export",
                )
                _save_history(
                    "product_dev",
                    {"product_type": product_types},
                    {"final_answer": result.get("final_answer", "")},
                    summary=f"类型: {', '.join(product_types)}",
                )
                with st.expander(t("t2.tool_calls")):
                    st.json(result.get("tool_calls", []))


with tab7:
    st.header(t("t7.header"))
    st.markdown(t("t7.desc"))

    col1, col2 = st.columns(2)
    with col1:
        account_id = st.text_input(t("t7.l_account"), value="default", key="upload_account")
    with col2:
        marketplace = st.selectbox(t("t7.l_marketplace"), ["US", "UK", "DE", "JP", "CA"], key="upload_marketplace")

    uploaded_files = st.file_uploader(
        t("t7.l_choose"),
        type=["csv"],
        accept_multiple_files=True,
        key="csv_uploader",
    )

    if st.button(t("t7.btn_import"), key="csv_import_btn"):
        if not uploaded_files:
            st.warning(t("t7.warn_no_file"))
        else:
            for uploaded in uploaded_files:
                with st.spinner(t("t7.spinner_import", name=uploaded.name)):
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
                    t(
                        "t7.success",
                        name=uploaded.name,
                        rows=result["rows_imported"],
                        type=result["csv_type"],
                        confidence=result["detection"]["confidence"],
                    )
                )
                if result.get("warnings"):
                    st.warning(t("t7.warnings", warnings="\n".join(result["warnings"])))
                with st.expander(t("t7.exp_mapping", name=uploaded.name)):
                    st.write(t("t7.matched", cols=result["detection"]["matched_columns"]))
                    if result["detection"]["missing_columns"]:
                        st.write(t("t7.missing", cols=result["detection"]["missing_columns"]))
            # Refresh cached SKU / account lists so newly imported data shows up.
            _invalidate_data_caches()

    with st.expander(t("t7.exp_types")):
        types_result = _call_api("GET", "/api/import-csv/types")
        if types_result.get("_api_error"):
            st.error(types_result["detail"])
        else:
            for t_row in types_result["types"]:
                st.markdown(f"**{t_row['name']}** (`{t_row['type']}`)")
                st.markdown(f"- {t('t7.r_required')}: {', '.join(t_row['required_columns'])}")
                st.markdown(f"- {t('t7.r_headers')}: {', '.join(t_row['recognisable_headers'])}")


with tab8:
    st.header(t("t8.header"))
    st.markdown(t("t8.desc"))

    refresh = st.button(t("t8.btn_refresh"), key="data_refresh_btn")
    if refresh:
        _invalidate_data_caches()

    overview = _call_api("GET", "/api/data/overview")
    if overview.get("_api_error"):
        st.error(overview["detail"])
    else:
        rows = overview.get("overview", [])
        if not rows:
            st.info(t("t8.empty"))
        else:
            df = pd.DataFrame(rows)
            df = df.rename(columns={
                "data_type": t("t8.col_type"),
                "account_id": t("t8.col_account"),
                "marketplace": t("t8.col_marketplace"),
                "sku_count": t("t8.col_skus"),
                "row_count": t("t8.col_rows"),
                "min_date": t("t8.col_min_date"),
                "max_date": t("t8.col_max_date"),
                "last_imported": t("t8.col_last_import"),
            })
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader(t("t8.delete_title"))

            # Build delete options from the overview rows.
            acct_pairs = sorted({(r["account_id"], r["marketplace"]) for r in rows})
            account_options = [f"{a[0]} / {a[1]}" for a in acct_pairs]
            type_options = ["all"] + sorted({r["data_type"] for r in rows})

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                sel_account = st.selectbox(t("t8.l_account"), account_options, key="del_account")
            with col_b:
                sel_type = st.selectbox(t("t8.l_type"), type_options, key="del_type")
            with col_c:
                st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
                delete_btn = st.button(t("t8.btn_delete"), key="del_btn", type="primary")

            if delete_btn:
                acc_id, mkt = sel_account.split(" / ", 1)
                csv_type = None if sel_type == "all" else sel_type
                with st.spinner(t("t8.spinner_delete")):
                    result = _call_api(
                        "DELETE",
                        f"/api/data?account_id={acc_id}&marketplace={mkt}"
                        + (f"&csv_type={csv_type}" if csv_type else ""),
                    )
                if result.get("_api_error"):
                    st.error(result["detail"])
                else:
                    deleted = result.get("deleted", {})
                    total = sum(deleted.values())
                    st.success(t("t8.delete_success", total=total, account=sel_account))
                    _invalidate_data_caches()
                    st.rerun()
