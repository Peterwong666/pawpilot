"""Tab 4 — Ops daily digest: portfolio metrics, alerts, LLM briefing."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from web.api_client import call_api, save_history
from web.i18n import t


def render() -> None:
    st.header(t("t4.header"))
    st.markdown(t("t4.desc"))
    if st.button(t("t4.btn_digest"), key="digest_btn"):
        with st.spinner(t("t4.spinner")):
            result = call_api("POST", "/api/digest")
        if result.get("_api_error"):
            st.error(result["detail"])
        else:
            digest = result.get("digest", {})
            sku_rows = digest.get("sku_rows", [])
            alerts = digest.get("alerts", [])
            acos_target = digest.get("acos_target_pct", 30.0)

            # ---- Metric cards ----
            if sku_rows:
                total_units = sum(r.get("units_7d", 0) for r in sku_rows)
                total_revenue = sum(r.get("revenue_7d", 0) for r in sku_rows)
                total_profit = sum(r.get("est_profit_7d", 0) for r in sku_rows)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(t("t4.m_total_units"), f"{total_units:,.0f}")
                c2.metric(t("t4.m_total_revenue"), f"${total_revenue:,.2f}")
                c3.metric(t("t4.m_total_profit"), f"${total_profit:,.2f}")
                c4.metric(t("t4.m_alerts"), f"{len(alerts)}", delta=f"{digest.get('alert_count', len(alerts))}")

                # ---- Charts ----
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    st.markdown(f"**{t('t4.chart_units')}**")
                    units_df = pd.DataFrame([
                        {"SKU": r["sku"], t("t4.m_units_7d"): r.get("units_7d", 0)}
                        for r in sku_rows
                    ])
                    st.bar_chart(units_df.set_index("SKU"), use_container_width=True)
                with col_chart2:
                    st.markdown(f"**{t('t4.chart_acos')}** (target={acos_target}%)")
                    acos_df = pd.DataFrame([
                        {"SKU": r["sku"], "ACOS%": r.get("acos_7d", 0)}
                        for r in sku_rows
                    ])
                    st.bar_chart(acos_df.set_index("SKU"), use_container_width=True)

                # ---- SKU table with inventory highlighting ----
                st.markdown(f"**{t('t4.table_title')}**")
                table_rows = []
                for r in sku_rows:
                    inv = r.get("inventory_status", "ok")
                    inv_label = {"ok": "✓", "low": "⚠", "out": "✕"}.get(inv, inv)
                    table_rows.append({
                        "SKU": r["sku"],
                        t("t4.col_units"): r.get("units_7d", 0),
                        t("t4.col_wow"): f"{r.get('units_wow_pct', 0):+.1f}%",
                        t("t4.col_revenue"): f"${r.get('revenue_7d', 0):,.2f}",
                        t("t4.col_margin"): f"{r.get('margin_pct', 0):.1f}%",
                        t("t4.col_acos"): f"{r.get('acos_7d', 0):.1f}%",
                        t("t4.col_rating"): f"{r.get('rating_7d', 0):.2f}",
                        t("t4.col_inv"): f"{inv_label} {r.get('days_of_cover', 0)}d",
                    })
                if table_rows:
                    df = pd.DataFrame(table_rows)
                    # Highlight low/out-of-stock rows
                    def _highlight_inv(row):
                        inv_cell = str(row.get(t("t4.col_inv"), ""))
                        if inv_cell.startswith("✕"):
                            return ["background-color: #ffe0e0"] * len(row)
                        if inv_cell.startswith("⚠"):
                            return ["background-color: #fff8e0"] * len(row)
                        return [""] * len(row)
                    st.dataframe(df.style.apply(_highlight_inv, axis=1), use_container_width=True, hide_index=True)

                # ---- Alerts ----
                if alerts:
                    st.markdown(f"**{t('t4.alerts_title')}** ({len(alerts)})")
                    for a in alerts:
                        sev = a.get("severity", "info")
                        icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "🔵")
                        with st.container():
                            st.markdown(
                                f"{icon} **[{a.get('sku','-')}] {a.get('type','')}** — {a.get('detail','')}"
                            )
                            if a.get("action"):
                                st.caption(f"→ {a['action']}")
            else:
                st.info(t("t4.no_data"))

            st.markdown(f"### {t('t4.digest_title')}")
            st.markdown(result["final_answer"])
            st.download_button(
                t("t4.btn_export"),
                data=result["final_answer"],
                file_name="ops_daily_digest.md",
                mime="text/markdown",
                key="digest_export",
            )
            save_history(
                "ops_digest",
                {},
                {"final_answer": result.get("final_answer", ""), "digest": digest},
                summary=f"{len(alerts)} alerts",
            )
            with st.expander(t("t2.tool_calls")):
                st.json(result.get("tool_calls", []))
