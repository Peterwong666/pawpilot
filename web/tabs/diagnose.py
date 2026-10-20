"""Tab 5 — Sales diagnosis: attribute sales changes to traffic/CVR/rating/ads/price."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from web.api_client import call_api, fetch_skus, save_history
from web.i18n import t


def render() -> None:
    st.header(t("t5.header"))
    sku_options = fetch_skus()
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
                result = call_api("POST", "/api/diagnose", {"sku": diagnose_sku, "days": diagnose_days})
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
                save_history(
                    "sales_diagnosis",
                    {"sku": diagnose_sku, "days": diagnose_days},
                    {"final_answer": result.get("final_answer", "")},
                    summary=f"SKU: {', '.join(diagnose_sku)}",
                )
                with st.expander(t("t2.tool_calls")):
                    st.json(result.get("tool_calls", []))
