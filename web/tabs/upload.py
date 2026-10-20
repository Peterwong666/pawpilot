"""Tab 7 — Data upload: import Seller Central / Advertising CSVs."""

from __future__ import annotations

import streamlit as st

from web.api_client import call_api, call_upload_api, invalidate_data_caches
from web.i18n import t


def render() -> None:
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
                    result = call_upload_api(
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
            invalidate_data_caches()

    with st.expander(t("t7.exp_types")):
        types_result = call_api("GET", "/api/import-csv/types")
        if types_result.get("_api_error"):
            st.error(types_result["detail"])
        else:
            for t_row in types_result["types"]:
                st.markdown(f"**{t_row['name']}** (`{t_row['type']}`)")
                st.markdown(f"- {t('t7.r_required')}: {', '.join(t_row['required_columns'])}")
                st.markdown(f"- {t('t7.r_headers')}: {', '.join(t_row['recognisable_headers'])}")
