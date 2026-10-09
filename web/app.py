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

st.title(t("app.title"))
st.markdown(t("app.subtitle"))

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
    provider = st.selectbox("LLM provider", ["deepseek", "qwen"], index=0)
    st.markdown("---")
    st.markdown(f"**{t('sidebar.scenarios')}**")
    st.markdown(f"- {t('sidebar.scen_policy')}")
    st.markdown(f"- {t('sidebar.scen_listing')}")
    st.markdown(f"- {t('sidebar.scen_reviews')}")
    st.markdown(f"- {t('sidebar.scen_digest')}")
    st.markdown(f"- {t('sidebar.scen_diagnose')}")
    st.markdown(f"- {t('sidebar.scen_voc')}")
    st.markdown(f"- {t('sidebar.scen_upload')}")


tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [
        t("tab.policy"),
        t("tab.listing"),
        t("tab.reviews"),
        t("tab.digest"),
        t("tab.diagnose"),
        t("tab.voc"),
        t("tab.upload"),
    ]
)


def _call_api(method: str, path: str, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the FastAPI backend synchronously."""
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
        return {"_api_error": True, "detail": t("err.backend_down", url=url)}


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


with tab1:
    st.header(t("t1.header"))
    query = st.text_input(
        t("t1.query_label"),
        value=t("t1.query_default"),
        key="policy_query",
    )
    if st.button(t("t1.btn_ask"), key="ask_btn"):
        with st.spinner(t("t1.spinner")):
            result = _call_api("POST", "/api/ask", {"query": query})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown(f"### {t('t1.answer')}")
            st.markdown(result["answer"])
            with st.expander(t("t1.sources")):
                for src in result.get("sources", []):
                    st.markdown(f"**{src.get('doc_id')}** — {src.get('section')}")
                    st.markdown(f"```{src.get('text')[:400]}...```")
            with st.expander(t("t1.usage")):
                st.json(result.get("usage", {}))


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
    sku_input = st.selectbox(
        t("t3.l_sku"),
        ["PP-RT-101", "PP-RT-102", "PP-RT-103", "PP-HR-201", "PP-HR-203", "PP-SB-302"],
        index=4,
        key="review_sku",
    )
    days_input = st.slider(t("t3.l_days"), min_value=7, max_value=365, value=90, key="review_days")
    if st.button(t("t3.btn_analyze"), key="review_btn"):
        with st.spinner(t("t3.spinner")):
            result = _call_api("POST", "/api/reviews", {"sku": sku_input, "days": days_input})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown(f"### {t('t3.analysis')}")
            st.markdown(result["final_answer"])
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
            st.markdown(f"### {t('t4.digest_title')}")
            st.markdown(result["final_answer"])
            with st.expander(t("t2.tool_calls")):
                st.json(result.get("tool_calls", []))


with tab5:
    st.header(t("t5.header"))
    diagnose_sku = st.selectbox(
        t("t5.l_sku"),
        ["PP-RT-101", "PP-RT-102", "PP-RT-103", "PP-HR-201", "PP-HR-203", "PP-SB-302"],
        index=1,
        key="diagnose_sku",
    )
    diagnose_days = st.slider(t("t5.l_days"), min_value=7, max_value=60, value=14, key="diagnose_days")
    if st.button(t("t5.btn_diagnose"), key="diagnose_btn"):
        with st.spinner(t("t5.spinner")):
            result = _call_api("POST", "/api/diagnose", {"sku": diagnose_sku, "days": diagnose_days})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown(f"### {t('t5.diagnosis')}")
            st.markdown(result["final_answer"])
            with st.expander(t("t2.tool_calls")):
                st.json(result.get("tool_calls", []))


with tab6:
    st.header(t("t6.header"))
    # Options are canonical English keys (the API only accepts these);
    # format_func renders the localized label so the payload stays valid
    # regardless of UI language.
    product_type = st.selectbox(
        t("t6.l_product_type"),
        ["rope toy", "harness", "feeder bowl"],
        index=0,
        key="product_type",
        format_func=lambda x: {
            "rope toy": t("t6.opt_rope"),
            "harness": t("t6.opt_harness"),
            "feeder bowl": t("t6.opt_feeder"),
        }[x],
    )
    if st.button(t("t6.btn_voc"), key="voc_btn"):
        with st.spinner(t("t6.spinner")):
            result = _call_api("POST", "/api/product-dev", {"product_type": product_type})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown(f"### {t('t6.report')}")
            st.markdown(result["final_answer"])
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

    with st.expander(t("t7.exp_types")):
        types_result = _call_api("GET", "/api/import-csv/types")
        if types_result.get("_api_error"):
            st.error(types_result["detail"])
        else:
            for t_row in types_result["types"]:
                st.markdown(f"**{t_row['name']}** (`{t_row['type']}`)")
                st.markdown(f"- {t('t7.r_required')}: {', '.join(t_row['required_columns'])}")
                st.markdown(f"- {t('t7.r_headers')}: {', '.join(t_row['recognisable_headers'])}")
