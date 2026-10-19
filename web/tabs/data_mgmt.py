"""Tab 8 — Data management: overview + delete imported operational data."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from web.api_client import call_api, invalidate_data_caches
from web.i18n import t


def render() -> None:
    st.header(t("t8.header"))
    st.markdown(t("t8.desc"))

    refresh = st.button(t("t8.btn_refresh"), key="data_refresh_btn")
    if refresh:
        invalidate_data_caches()

    overview = call_api("GET", "/api/data/overview")
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
                    result = call_api(
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
                    invalidate_data_caches()
                    st.rerun()
