"""Tab 6 — Product dev VOC: mine competitor reviews for unmet needs."""

from __future__ import annotations

import streamlit as st

from web.api_client import call_api, fetch_product_types, save_history
from web.i18n import t


def render() -> None:
    st.header(t("t6.header"))
    # Options are canonical English keys fetched from the backend (competitor_reviews table);
    # format_func renders the localized label so the payload stays valid regardless of UI language.
    pt_options = fetch_product_types()
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
                result = call_api("POST", "/api/product-dev", {"product_type": product_types})
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
                save_history(
                    "product_dev",
                    {"product_type": product_types},
                    {"final_answer": result.get("final_answer", "")},
                    summary=f"类型: {', '.join(product_types)}",
                )
                with st.expander(t("t2.tool_calls")):
                    st.json(result.get("tool_calls", []))
