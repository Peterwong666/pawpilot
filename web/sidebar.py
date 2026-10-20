"""Sidebar panels for the PawPilot Streamlit UI.

Two render entry points, called from ``app.py`` in visual order:
1. ``render_settings`` — language, LLM provider, scenario list.
2. ``render_data_context`` — account / marketplace / demo-data toggle,
   plus the history and request-stats expanders.
"""

from __future__ import annotations

import streamlit as st

from web.api_client import SCENARIO_LABELS, fetch_accounts, fetch_history, fetch_stats
from web.i18n import DEFAULT_LANG, t

_SCENARIO_KEYS = (
    "sidebar.scen_policy",
    "sidebar.scen_listing",
    "sidebar.scen_reviews",
    "sidebar.scen_digest",
    "sidebar.scen_diagnose",
    "sidebar.scen_voc",
    "sidebar.scen_upload",
    "sidebar.scen_dashboard",
)


def render_settings() -> None:
    """Render the top sidebar block: language, provider, scenario list."""
    with st.sidebar:
        st.header(t("sidebar.settings"))
        st.selectbox(
            t("sidebar.lang"),
            ["zh", "en"],
            index=0 if st.session_state.get("lang", DEFAULT_LANG) == "zh" else 1,
            key="lang",
            format_func=lambda x: t("sidebar.lang_option_zh") if x == "zh" else t("sidebar.lang_option_en"),
        )
        st.selectbox("LLM provider", ["deepseek", "qwen"], index=0, key="provider")

        st.markdown("---")
        st.markdown(f"**{t('sidebar.scenarios')}**")
        for key in _SCENARIO_KEYS:
            st.markdown(f"- {t(key)}")


def render_data_context() -> None:
    """Render the data-context sidebar block (account, marketplace, history, stats)."""
    with st.sidebar:
        st.markdown("---")
        st.subheader(t("sidebar.data_context"))

        accounts = fetch_accounts()
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
            records = fetch_history()
            if not records:
                st.caption(t("sidebar.history_empty"))
            else:
                for rec in records[:20]:
                    label = SCENARIO_LABELS.get(rec.get("scenario", ""), rec.get("scenario", ""))
                    ts = (rec.get("created_at") or "")[:16].replace("T", " ")
                    summary = rec.get("summary") or ""
                    if summary:
                        summary = summary[:40] + ("…" if len(summary) > 40 else "")
                    if st.button(f"📋 {label} — {ts}", key=f"hist_{rec['id']}"):
                        st.session_state["_history_view"] = rec
                        st.rerun()

        with st.expander(t("sidebar.stats"), expanded=False):
            if st.button(t("sidebar.stats_refresh"), key="stats_refresh"):
                st.rerun()
            stats = fetch_stats()
            if not stats:
                st.caption(t("sidebar.stats_unavailable"))
            else:
                st.metric(t("sidebar.stats_requests"), stats.get("requests_total", 0))
                st.metric(t("sidebar.stats_avg_latency"), f"{stats.get('avg_latency_ms', 0):.0f} ms")
                hit_rate = stats.get("retrieval_hit_rate")
                st.metric(
                    t("sidebar.stats_hit_rate"),
                    f"{hit_rate * 100:.0f}%" if hit_rate is not None else "—",
                )
