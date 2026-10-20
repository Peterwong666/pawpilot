"""Tab 3 — Review analysis for one or more SKUs."""

from __future__ import annotations

import streamlit as st

from web.api_client import call_api, fetch_skus, save_history
from web.i18n import t


def render() -> None:
    st.header(t("t3.header"))
    sku_options = fetch_skus()
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
                result = call_api("POST", "/api/reviews", {"sku": sku_input, "days": days_input})
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
                save_history(
                    "review_analysis",
                    {"sku": sku_input, "days": days_input},
                    {"final_answer": result.get("final_answer", "")},
                    summary=f"SKU: {', '.join(sku_input)}",
                )
                with st.expander(t("t2.tool_calls")):
                    st.json(result.get("tool_calls", []))
