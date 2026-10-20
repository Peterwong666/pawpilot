"""Tab 2 — Listing generator + compliance check."""

from __future__ import annotations

import streamlit as st

from web.api_client import call_api
from web.i18n import t


def render() -> None:
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
            result = call_api("POST", "/api/listing", {"product_info": product_info})
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            st.markdown(f"### {t('t2.result')}")
            st.markdown(result["final_answer"])
            with st.expander(t("t2.tool_calls")):
                st.json(result.get("tool_calls", []))
