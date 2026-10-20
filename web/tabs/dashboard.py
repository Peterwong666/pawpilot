"""Tab 9 — Sales trend chart + inventory dashboard (plotly).

Data comes from ``/api/metrics/sales-trend`` and ``/api/metrics/inventory``,
which read from the HybridDataStore (simulated data in demo mode, real
overlays once CSVs are imported), so this tab works in PAWPILOT_DEMO_MODE.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from web.api_client import call_api
from web.i18n import t

_STATUS_COLORS = {"ok": "#2e7d32", "low": "#f9a825", "out": "#c62828"}


def _render_trend() -> None:
    """Sales / revenue trend lines per SKU."""
    st.subheader(t("t9.trend_sub"))
    days = st.slider(t("t9.days"), min_value=7, max_value=90, value=30, key="t9_days")
    result = call_api("GET", "/api/metrics/sales-trend", {"days": days})
    if result.get("_api_error"):
        st.error(result["detail"])
        return
    points = result.get("trend") or []
    if not points:
        st.info(t("t9.empty"))
        return
    df = pd.DataFrame(points)
    df["date"] = pd.to_datetime(df["date"])

    st.markdown(f"**{t('t9.units_chart')}**")
    units_fig = px.line(df, x="date", y="units", color="sku", markers=True)
    units_fig.update_layout(xaxis_title=None, yaxis_title=t("t9.col_units"), legend_title="SKU")
    st.plotly_chart(units_fig, use_container_width=True)

    st.markdown(f"**{t('t9.revenue_chart')}**")
    revenue_fig = px.line(df, x="date", y="revenue", color="sku", markers=True)
    revenue_fig.update_layout(xaxis_title=None, yaxis_title=t("t9.col_revenue"), legend_title="SKU")
    st.plotly_chart(revenue_fig, use_container_width=True)


def _render_inventory() -> None:
    """Inventory board: KPI cards, days-of-cover chart, status table."""
    st.subheader(t("t9.inv_sub"))
    window = st.slider(t("t9.window"), min_value=7, max_value=60, value=14, key="t9_window")
    result = call_api("GET", "/api/metrics/inventory", {"window_days": window})
    if result.get("_api_error"):
        st.error(result["detail"])
        return
    items = result.get("inventory") or []
    if not items:
        st.info(t("t9.empty"))
        return
    idf = pd.DataFrame(items)

    # ---- KPI cards ----
    at_risk = int((idf["status"] != "ok").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric(t("t9.m_skus"), len(idf))
    c2.metric(t("t9.m_at_risk"), at_risk)
    c3.metric(t("t9.m_on_hand"), f"{int(idf['on_hand'].sum()):,}")

    # ---- Days-of-cover vs lead-time chart ----
    st.markdown(f"**{t('t9.cover_chart')}**")
    chart_df = idf.copy()
    # days_of_cover is None for dead SKUs (no sales in window); plot as 0.
    chart_df["days_of_cover"] = chart_df["days_of_cover"].fillna(0.0)
    status_labels = {
        "ok": t("t9.status_ok"),
        "low": t("t9.status_low"),
        "out": t("t9.status_out"),
    }
    chart_df["status_label"] = chart_df["status"].map(status_labels)
    cover_fig = px.bar(
        chart_df,
        x="sku",
        y="days_of_cover",
        color="status_label",
        color_discrete_map={
            status_labels["ok"]: _STATUS_COLORS["ok"],
            status_labels["low"]: _STATUS_COLORS["low"],
            status_labels["out"]: _STATUS_COLORS["out"],
        },
    )
    # Overlay restock lead time as diamond markers so cover < lead_time is visible.
    cover_fig.add_scatter(
        x=chart_df["sku"],
        y=chart_df["lead_time_days"],
        mode="markers",
        name=t("t9.lead_time_marker"),
        marker={"symbol": "diamond", "size": 12, "color": "#212121"},
    )
    cover_fig.update_layout(
        xaxis_title="SKU",
        yaxis_title=t("t9.col_cover"),
        legend_title=None,
    )
    st.plotly_chart(cover_fig, use_container_width=True)

    # ---- Status table with row highlighting ----
    table_rows = [
        {
            "SKU": row["sku"],
            t("t9.col_on_hand"): row["on_hand"],
            t("t9.col_inbound"): row["inbound"],
            t("t9.col_avg_daily"): f"{row['avg_daily_units']:.1f}",
            t("t9.col_cover"): "—" if row["days_of_cover"] is None else f"{row['days_of_cover']:.0f}d",
            t("t9.col_lead_time"): f"{row['lead_time_days']}d",
            t("t9.col_status"): status_labels.get(row["status"], row["status"]),
        }
        for row in items
    ]
    table = pd.DataFrame(table_rows)

    def _highlight(row: pd.Series) -> list[str]:
        status_cell = str(row[t("t9.col_status")])
        if status_cell == status_labels["out"]:
            return ["background-color: #ffe0e0"] * len(row)
        if status_cell == status_labels["low"]:
            return ["background-color: #fff8e0"] * len(row)
        return [""] * len(row)

    st.dataframe(table.style.apply(_highlight, axis=1), use_container_width=True, hide_index=True)


def render() -> None:
    st.header(t("t9.header"))
    st.caption(t("t9.caption"))
    _render_trend()
    st.markdown("---")
    _render_inventory()
