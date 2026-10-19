"""Tab 1 — Amazon policy & SOP Q&A (chat interface)."""

from __future__ import annotations

import streamlit as st

from web.api_client import call_api
from web.i18n import t


def render() -> None:
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
            result = call_api("POST", "/api/ask", {"query": query})
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
