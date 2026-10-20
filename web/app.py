"""Streamlit demo UI for PawPilot — entry point and tab routing only.

Nine scenario tabs (implementations live in ``web/tabs/``):
1. Policy Q&A — ask Amazon policy questions.
2. Listing Generator — generate and review a listing from product info.
3. Review Analysis — analyze reviews for a SKU.
4. Ops Daily Digest — portfolio-level daily operations briefing.
5. Sales Diagnosis — attribute a SKU's sales change to traffic/CVR/rating/ads/price.
6. Product Dev VOC — mine competitor reviews for unmet needs and improvements.
7. Data Upload — import Seller Central / Advertising CSVs.
8. Data Management — overview and delete imported operational data.
9. Dashboard — sales trend chart + inventory board (plotly).

Backend calls live in ``web/api_client.py``; sidebar panels in
``web/sidebar.py``. All user-visible strings go through ``t(key)`` so the
UI can switch between Chinese (default) and English via the sidebar selector.
"""

from __future__ import annotations

import streamlit as st

from web import sidebar
from web.api_client import SCENARIO_LABELS
from web.embedded_api import ensure_demo_api
from web.i18n import init_lang, t
from web.tabs import (
    dashboard,
    data_mgmt,
    diagnose,
    digest,
    listing,
    policy,
    reviews,
    upload,
    voc,
)

# On single-process hosts (Streamlit Community Cloud), demo mode runs the
# FastAPI backend in-process; locally with PAWPILOT_API_URL set this is a no-op.
ensure_demo_api()

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
        label = SCENARIO_LABELS.get(_hist_view.get("scenario", ""), _hist_view.get("scenario", ""))
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

# Sidebar top block: language, provider, scenario list.
sidebar.render_settings()

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(
    [
        t("tab.policy"),
        t("tab.listing"),
        t("tab.reviews"),
        t("tab.digest"),
        t("tab.diagnose"),
        t("tab.voc"),
        t("tab.upload"),
        t("tab.data_mgmt"),
        t("tab.dashboard"),
    ]
)

with tab1:
    policy.render()
with tab2:
    listing.render()
with tab3:
    reviews.render()
with tab4:
    digest.render()
with tab5:
    diagnose.render()
with tab6:
    voc.render()
with tab7:
    upload.render()
with tab8:
    data_mgmt.render()
with tab9:
    dashboard.render()

# Sidebar bottom block: data context (account / marketplace / simulated
# data toggle), history panel, request stats. Rendered after the tabs so it
# appears below the settings block, matching the pre-split visual order.
sidebar.render_data_context()
