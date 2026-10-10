"""Internationalisation helpers for the PawPilot Streamlit UI.

Usage at the top of ``app.py``::

    from web.i18n import t, init_lang

    init_lang()          # default Chinese, respects session_state override
    # ... later in script ...
    st.title(t("app.title"))

Adding a new UI string: add an entry to both dictionaries below with the
same key, then reference it via ``t("key")`` in app.py. All keys are flat
dot-separated names so lookups are O(1).
"""

from __future__ import annotations

import streamlit as st

LANG_KEY = "lang"
DEFAULT_LANG = "zh"

zh: dict[str, str] = {
    # 全局 ---------------------------------------------------------------
    "app.title": "🐾 PawPilot — 亚马逊宠物用品运营 Copilot",
    "app.subtitle": "RAG 知识库 + Agent 工作流，服务跨境电商运营。",
    "onboarding.title": "欢迎使用 PawPilot",
    "onboarding.intro": "我是你的亚马逊运营 Copilot。按以下顺序开始：",
    "onboarding.steps": (
        "1️⃣ **数据上传**：导入你的 Seller Central / Advertising CSV（填账号和站点）\n\n"
        "2️⃣ **数据管理**：确认数据已导入，可删除错误数据\n\n"
        "3️⃣ **侧边栏选择账号/站点**：选择你的店铺，关闭\"叠加演示数据\"只看真实数据\n\n"
        "4️⃣ **运营日报**：一键生成全店指标看板和预警\n\n"
        "5️⃣ **销量诊断/评论分析**：多选 SKU 批量分析\n\n"
        "6️⃣ **报告导出/历史记录**：导出 MD 报告，侧边栏回看历史分析"
    ),
    "onboarding.got_it": "开始使用",
    "onboarding.dont_show": "不再提示",
    "sidebar.settings": "设置",
    "sidebar.lang": "界面语言",
    "sidebar.lang_option_zh": "中文",
    "sidebar.lang_option_en": "English",
    "sidebar.provider": "LLM 提供方",
    "sidebar.scenarios": "场景",
    "sidebar.scen_policy": "政策与 SOP 问答",
    "sidebar.scen_listing": "Listing 生成与合规检查",
    "sidebar.scen_reviews": "评论分析",
    "sidebar.scen_digest": "运营日报",
    "sidebar.scen_diagnose": "销量诊断",
    "sidebar.scen_voc": "产品开发 VOC",
    "sidebar.scen_upload": "数据上传",
    "sidebar.data_context": "数据上下文",
    "sidebar.account": "账号",
    "sidebar.account_help": "选择要分析的店铺账号。多账号数据相互隔离。",
    "sidebar.marketplace": "站点",
    "sidebar.marketplace_help": "选择亚马逊站点（US/UK/DE 等）。",
    "sidebar.use_simulated": "叠加演示数据",
    "sidebar.use_simulated_help": "开启时会在你的真实数据上叠加 PawPilot 示例 SKU；关闭后仅显示你导入的真实数据。",
    "sidebar.history": "历史记录",
    "sidebar.history_refresh": "刷新",
    "sidebar.history_empty": "暂无历史记录，完成一次分析后会自动保存。",
    "sidebar.history_close": "关闭",
    "err.backend_down":
        "无法连接 PawPilot API（{url}）。请确认 FastAPI 后端已启动：\n\n"
        "uv run uvicorn app.api.main:app --reload",
    "err.backend_down_short":
        "无法连接 PawPilot API（{url}）。请确认 FastAPI 后端已启动。",
    "err.http_error":
        "API 返回错误（HTTP {code}）：{detail}",

    # Tab 名 -------------------------------------------------------------
    "tab.policy": "政策与 SOP 问答",
    "tab.listing": "Listing 生成与合规",
    "tab.reviews": "评论分析",
    "tab.digest": "运营日报",
    "tab.diagnose": "销量诊断",
    "tab.voc": "产品开发 VOC",
    "tab.upload": "数据上传",
    "tab.data_mgmt": "数据管理",

    # Tab 1 — Policy Q&A ------------------------------------------------
    "t1.header": "亚马逊政策与 SOP 问答",
    "t1.query_label": "提问",
    "t1.query_default": "宠物用品 Listing 的标题最大长度是多少？",
    "t1.btn_ask": "提问",
    "t1.spinner": "检索并生成答案中…",
    "t1.answer": "答案",
    "t1.sources": "来源",
    "t1.usage": "调用用量",
    "t1.clear_chat": "清空对话",

    # Tab 2 — Listing Generator -----------------------------------------
    "t2.header": "Listing 生成 + 合规检查",
    "t2.l_sku": "SKU",
    "t2.l_product_type": "产品类型",
    "t2.l_dog_weight": "目标犬重",
    "t2.l_size": "尺寸",
    "t2.l_color": "颜色",
    "t2.l_material": "材质",
    "t2.l_key_feature": "核心卖点",
    "t2.l_packaging": "包装",
    "t2.custom_title": "自定义属性",
    "t2.custom_name": "属性名",
    "t2.custom_name_ph": "属性名（如 scent、warranty）",
    "t2.custom_value": "属性值",
    "t2.custom_value_ph": "属性值",
    "t2.custom_add": "添加",
    "t2.btn_gen": "生成 Listing",
    "t2.spinner": "生成并审核 Listing 中…",
    "t2.result": "结果",
    "t2.tool_calls": "工具调用",

    # Tab 3 — Review Analysis -------------------------------------------
    "t3.header": "评论分析",
    "t3.l_sku": "SKU",
    "t3.l_sku_help": "可选择一个或多个 SKU 进行对比分析",
    "t3.l_days": "天数",
    "t3.btn_analyze": "分析",
    "t3.spinner": "分析评论中…",
    "t3.analysis": "分析结果",
    "t3.btn_export": "导出报告 (MD)",
    "t3.warn_no_sku": "请至少选择一个 SKU。",

    # Tab 4 — Ops Daily Digest ------------------------------------------
    "t4.header": "运营日报",
    "t4.desc": "每日 portfolio 简报：销量环比、利润、库存覆盖、ACOS 与评分预警。",
    "t4.btn_digest": "生成日报",
    "t4.spinner": "生成日报中…",
    "t4.digest_title": "运营日报",
    "t4.btn_export": "导出报告 (MD)",
    "t4.m_total_units": "7日总销量",
    "t4.m_total_revenue": "7日总营收",
    "t4.m_total_profit": "7日总利润",
    "t4.m_alerts": "预警数",
    "t4.chart_units": "各 SKU 7日销量",
    "t4.m_units_7d": "销量(7d)",
    "t4.chart_acos": "各 SKU ACOS",
    "t4.table_title": "SKU 运营明细",
    "t4.col_units": "销量",
    "t4.col_wow": "环比",
    "t4.col_revenue": "营收",
    "t4.col_margin": "利润率",
    "t4.col_acos": "ACOS",
    "t4.col_rating": "评分",
    "t4.col_inv": "库存",
    "t4.alerts_title": "预警与建议",
    "t4.no_data": "当前账号/站点暂无近 7 天运营数据。请先在「数据上传」Tab 导入 CSV，或在侧边栏开启「叠加演示数据」查看示例。",

    # Tab 5 — Sales Diagnosis -------------------------------------------
    "t5.header": "销量诊断",
    "t5.l_sku": "SKU",
    "t5.l_sku_help": "可选择一个或多个 SKU 批量诊断",
    "t5.l_days": "天数",
    "t5.btn_diagnose": "诊断",
    "t5.spinner": "正在诊断销量异动…",
    "t5.diagnosis": "诊断结果",
    "t5.warn_no_sku": "请至少选择一个 SKU。",
    "t5.m_units": "销量",
    "t5.m_sessions": "会话数",
    "t5.m_cvr": "转化率(%)",
    "t5.m_price": "售价",
    "t5.m_ad_spend": "广告花费",
    "t5.m_rating": "平均评分",
    "t5.btn_export": "导出报告 (MD)",

    # Tab 6 — Product Dev VOC -------------------------------------------
    "t6.header": "产品开发 VOC",
    "t6.l_product_type": "产品类型",
    "t6.l_product_type_help": "可选择一个或多个产品线对比挖掘竞品机会",
    "t6.opt_rope": "绳玩具",
    "t6.opt_harness": "胸背带",
    "t6.opt_feeder": "慢食碗",
    "t6.btn_voc": "分析 VOC",
    "t6.spinner": "挖掘竞品评论中的产品机会…",
    "t6.report": "产品开发报告",
    "t6.btn_export": "导出报告 (MD)",
    "t6.warn_no_product_type": "请至少选择一个产品类型。",

    # Tab 7 — Data Upload -----------------------------------------------
    "t7.header": "数据上传 — Seller Central / Advertising CSV",
    "t7.desc": (
        "上传亚马逊后台导出的 CSV，自动识别报表类型并覆盖到运营数据层。"
        "支持 Business Report（销量）、Advertising Report（广告）、"
        "FBA Inventory Report（库存）、SKU 成本表（利润）。"
        "导入后，诊断 / 日报 / 库存 / 利润工具会优先使用真实数据。"
    ),
    "t7.l_account": "Account ID（店铺/账号）",
    "t7.l_marketplace": "市场",
    "t7.l_choose": "选择 CSV 文件（可多选）",
    "t7.btn_import": "导入数据",
    "t7.warn_no_file": "请先选择 CSV 文件。",
    "t7.spinner_import": "正在导入 {name}…",
    "t7.success": (
        "**{name}** — {rows} 行导入成功 "
        "（检测类型：{type}，置信度：{confidence}）"
    ),
    "t7.warnings": "警告：{warnings}",
    "t7.exp_mapping": "列映射详情 — {name}",
    "t7.matched": "匹配列：{cols}",
    "t7.missing": "缺失列（已使用默认值）：{cols}",
    "t7.exp_types": "支持的 CSV 类型",
    "t7.r_required": "必需列",
    "t7.r_headers": "可识别表头",

    # Tab 8 — Data Management -------------------------------------------
    "t8.header": "数据管理",
    "t8.desc": "查看已导入的运营数据概览，按账号/站点/类型删除不需要的数据。",
    "t8.btn_refresh": "刷新",
    "t8.empty": "暂无已导入的运营数据。请先在「数据上传」标签页导入 CSV。",
    "t8.col_type": "数据类型",
    "t8.col_account": "账号",
    "t8.col_marketplace": "站点",
    "t8.col_skus": "SKU 数",
    "t8.col_rows": "行数",
    "t8.col_min_date": "起始日期",
    "t8.col_max_date": "结束日期",
    "t8.col_last_import": "最近导入",
    "t8.delete_title": "删除数据",
    "t8.l_account": "账号 / 站点",
    "t8.l_type": "数据类型",
    "t8.btn_delete": "删除选中数据",
    "t8.spinner_delete": "正在删除并重建数据层…",
    "t8.delete_success": "已删除 {account} 的 {total} 行数据。",

    # Streamlit 框架级 UI 覆盖 -----------------------------------------
    "menu.about": (
        "### PawPilot\n"
        "亚马逊宠物用品运营 Copilot — RAG + Agent + MCP\n\n"
        "**如何配置 LLM**\n"
        "1. 复制 `.env.example` 为 `.env`；\n"
        "2. 填入任一模型 Key：`DEEPSEEK_API_KEY` 或 `DASHSCOPE_API_KEY`；\n"
        "3. 填入 `SILICONFLOW_API_KEY`（嵌入/重排序，有免费额度）；\n"
        "4. 重启 API 服务，在侧边栏选择对应提供方即可。"
    ),
    "menu.get_help": "### 使用说明\n在侧边栏选择界面语言与 LLM 提供方后，从 7 个场景中任选一个开始体验。",
    "menu.report_bug": "### 反馈\n请将问题描述、复现步骤与截图整理后提交到项目仓库。",
}


en: dict[str, str] = {
    "app.title": "🐾 PawPilot — Amazon Pet-Supplies Operations Copilot",
    "app.subtitle": "RAG knowledge base + Agent workflows for cross-border e-commerce operations.",
    "onboarding.title": "Welcome to PawPilot",
    "onboarding.intro": "I'm your Amazon operations Copilot. Get started in this order:",
    "onboarding.steps": (
        "1️⃣ **Data Upload**: Import your Seller Central / Advertising CSV (fill in account & marketplace)\n\n"
        "2️⃣ **Data Management**: Confirm imported data, delete incorrect records\n\n"
        "3️⃣ **Sidebar: select account/marketplace**: Pick your store, turn off \"Overlay demo data\" to see only real data\n\n"
        "4️⃣ **Ops Daily Digest**: Generate a full-store metrics dashboard and alerts\n\n"
        "5️⃣ **Sales Diagnosis / Review Analysis**: Multi-select SKUs for batch analysis\n\n"
        "6️⃣ **Export / History**: Export MD reports, review past analyses in the sidebar"
    ),
    "onboarding.got_it": "Get Started",
    "onboarding.dont_show": "Don't show again",
    "sidebar.settings": "Settings",
    "sidebar.lang": "Language",
    "sidebar.lang_option_zh": "中文",
    "sidebar.lang_option_en": "English",
    "sidebar.provider": "LLM provider",
    "sidebar.scenarios": "Scenarios",
    "sidebar.scen_policy": "Policy Q&A",
    "sidebar.scen_listing": "Listing Generator + Compliance",
    "sidebar.scen_reviews": "Review Analysis",
    "sidebar.scen_digest": "Ops Daily Digest",
    "sidebar.scen_diagnose": "Sales Diagnosis",
    "sidebar.scen_voc": "Product Dev VOC",
    "sidebar.scen_upload": "Data Upload",
    "sidebar.data_context": "Data Context",
    "sidebar.account": "Account",
    "sidebar.account_help": "Select the store account to analyze. Data is isolated per account.",
    "sidebar.marketplace": "Marketplace",
    "sidebar.marketplace_help": "Select the Amazon marketplace (US/UK/DE, etc.).",
    "sidebar.use_simulated": "Overlay demo data",
    "sidebar.use_simulated_help": "When on, PawPilot sample SKUs are shown alongside your real data. Turn off to see only your imported data.",
    "sidebar.history": "History",
    "sidebar.history_refresh": "Refresh",
    "sidebar.history_empty": "No history yet. Run an analysis to save it automatically.",
    "sidebar.history_close": "Close",
    "err.backend_down":
        "Cannot connect to PawPilot API at {url}. "
        "Please make sure the FastAPI backend is running:\n\n"
        "uv run uvicorn app.api.main:app --reload",
    "err.backend_down_short":
        "Cannot connect to PawPilot API at {url}. "
        "Please make sure the FastAPI backend is running.",
    "err.http_error":
        "API returned an error (HTTP {code}): {detail}",

    "tab.policy": "Policy Q&A",
    "tab.listing": "Listing + Compliance",
    "tab.reviews": "Review Analysis",
    "tab.digest": "Ops Daily Digest",
    "tab.diagnose": "Sales Diagnosis",
    "tab.voc": "Product Dev VOC",
    "tab.upload": "Data Upload",
    "tab.data_mgmt": "Data Management",

    "t1.header": "Amazon Policy & SOP Q&A",
    "t1.query_label": "Ask a question",
    "t1.query_default": "What is the maximum title length for Pet Supplies listings?",
    "t1.btn_ask": "Ask",
    "t1.spinner": "Retrieving and generating answer...",
    "t1.answer": "Answer",
    "t1.sources": "Sources",
    "t1.usage": "Usage",
    "t1.clear_chat": "Clear chat",

    "t2.header": "Listing Generator + Compliance Check",
    "t2.l_sku": "SKU",
    "t2.l_product_type": "Product type",
    "t2.l_dog_weight": "Target dog weight",
    "t2.l_size": "Size",
    "t2.l_color": "Color",
    "t2.l_material": "Material",
    "t2.l_key_feature": "Key feature",
    "t2.l_packaging": "Packaging",
    "t2.custom_title": "Custom Attributes",
    "t2.custom_name": "Name",
    "t2.custom_name_ph": "e.g. scent, warranty",
    "t2.custom_value": "Value",
    "t2.custom_value_ph": "value",
    "t2.custom_add": "Add",
    "t2.btn_gen": "Generate Listing",
    "t2.spinner": "Generating and reviewing listing...",
    "t2.result": "Result",
    "t2.tool_calls": "Tool calls",

    "t3.header": "Review Analysis",
    "t3.l_sku": "SKU",
    "t3.l_sku_help": "Select one or more SKUs for comparative analysis",
    "t3.l_days": "Days",
    "t3.btn_analyze": "Analyze",
    "t3.spinner": "Analyzing reviews...",
    "t3.analysis": "Analysis",
    "t3.btn_export": "Export Report (MD)",
    "t3.warn_no_sku": "Please select at least one SKU.",

    "t4.header": "Ops Daily Digest",
    "t4.desc": "Portfolio-level daily briefing: sales WoW, margin, inventory cover, ACOS, and rating alerts.",
    "t4.btn_digest": "Generate digest",
    "t4.spinner": "Generating daily digest...",
    "t4.digest_title": "Daily Digest",
    "t4.btn_export": "Export Report (MD)",
    "t4.m_total_units": "7d Total Units",
    "t4.m_total_revenue": "7d Total Revenue",
    "t4.m_total_profit": "7d Total Profit",
    "t4.m_alerts": "Alerts",
    "t4.chart_units": "Units by SKU (7d)",
    "t4.m_units_7d": "Units(7d)",
    "t4.chart_acos": "ACOS by SKU",
    "t4.table_title": "SKU Operations Detail",
    "t4.col_units": "Units",
    "t4.col_wow": "WoW",
    "t4.col_revenue": "Revenue",
    "t4.col_margin": "Margin",
    "t4.col_acos": "ACOS",
    "t4.col_rating": "Rating",
    "t4.col_inv": "Inventory",
    "t4.alerts_title": "Alerts & Recommendations",
    "t4.no_data": "No operational data for the last 7 days in this account/marketplace. Please import CSV in the Data Upload tab, or enable Overlay demo data in the sidebar to see sample data.",

    "t5.header": "Sales Diagnosis",
    "t5.l_sku": "SKU",
    "t5.l_sku_help": "Select one or more SKUs for batch diagnosis",
    "t5.l_days": "Days",
    "t5.btn_diagnose": "Diagnose",
    "t5.spinner": "Diagnosing sales anomaly...",
    "t5.diagnosis": "Diagnosis",
    "t5.warn_no_sku": "Please select at least one SKU.",
    "t5.m_units": "Units",
    "t5.m_sessions": "Sessions",
    "t5.m_cvr": "CVR(%)",
    "t5.m_price": "Price",
    "t5.m_ad_spend": "Ad Spend",
    "t5.m_rating": "Avg Rating",
    "t5.btn_export": "Export Report (MD)",

    "t6.header": "Product Dev VOC",
    "t6.l_product_type": "Product type",
    "t6.l_product_type_help": "Select one or more product lines to mine competitor opportunities",
    "t6.opt_rope": "rope toy",
    "t6.opt_harness": "harness",
    "t6.opt_feeder": "feeder bowl",
    "t6.btn_voc": "Analyze VOC",
    "t6.spinner": "Mining competitor reviews for product opportunities...",
    "t6.report": "Product Development Report",
    "t6.btn_export": "Export Report (MD)",
    "t6.warn_no_product_type": "Please select at least one product type.",

    "t7.header": "Data Upload — Seller Central / Advertising CSV",
    "t7.desc": (
        "Upload CSV exports from Amazon Seller Central. Columns are auto-detected "
        "and mapped; imported rows overlay the simulated operational dataset per "
        "SKU+date. All tools (diagnose, digest, inventory, profit) prefer real "
        "numbers once imported."
    ),
    "t7.l_account": "Account ID (shop / account)",
    "t7.l_marketplace": "Marketplace",
    "t7.l_choose": "Choose CSV file(s) — multi-select supported",
    "t7.btn_import": "Import",
    "t7.warn_no_file": "Please choose a CSV file first.",
    "t7.spinner_import": "Importing {name}...",
    "t7.success": (
        "**{name}** — {rows} rows imported "
        "(detected type: {type}, confidence: {confidence})"
    ),
    "t7.warnings": "Warnings: {warnings}",
    "t7.exp_mapping": "Column mapping — {name}",
    "t7.matched": "Matched columns: {cols}",
    "t7.missing": "Missing columns (defaults used): {cols}",
    "t7.exp_types": "Supported CSV types",
    "t7.r_required": "Required columns",
    "t7.r_headers": "Recognisable headers",

    # Tab 8 — Data Management -------------------------------------------
    "t8.header": "Data Management",
    "t8.desc": "View imported operational data and delete by account / marketplace / type.",
    "t8.btn_refresh": "Refresh",
    "t8.empty": "No imported operational data yet. Please upload CSVs in the Data Upload tab.",
    "t8.col_type": "Type",
    "t8.col_account": "Account",
    "t8.col_marketplace": "Marketplace",
    "t8.col_skus": "SKUs",
    "t8.col_rows": "Rows",
    "t8.col_min_date": "From",
    "t8.col_max_date": "To",
    "t8.col_last_import": "Last import",
    "t8.delete_title": "Delete data",
    "t8.l_account": "Account / Marketplace",
    "t8.l_type": "Data type",
    "t8.btn_delete": "Delete selected",
    "t8.spinner_delete": "Deleting and rebuilding data layer...",
    "t8.delete_success": "Deleted {total} rows for {account}.",

    # Streamlit framework UI overrides (menu_items + CSS-hidden Deploy)
    "menu.about": (
        "### PawPilot\n"
        "Amazon Pet-Supplies Operations Copilot — RAG + Agent + MCP\n\n"
        "**How to configure the LLM**\n"
        "1. Copy `.env.example` to `.env`;\n"
        "2. Add one model key: `DEEPSEEK_API_KEY` or `DASHSCOPE_API_KEY`;\n"
        "3. Add `SILICONFLOW_API_KEY` (embedding / rerank, free tier);\n"
        "4. Restart the API and pick the matching provider in the sidebar."
    ),
    "menu.get_help": "### How to use\nPick a language and LLM provider in the sidebar, then open any of the 7 scenario tabs.",
    "menu.report_bug": "### Report a bug\nPlease include a concise description, reproduction steps, and screenshots in the project repository.",
}


_dicts: dict[str, dict[str, str]] = {"zh": zh, "en": en}


def init_lang() -> None:
    """Ensure ``st.session_state.lang`` is initialised.

    Safe to call multiple times; idempotent. Defaults to Chinese on first
    load. The actual selectbox rendering happens in ``app.py`` so that the
    UI stays in that file; this helper only seeds the session state.
    """
    if LANG_KEY not in st.session_state:
        st.session_state[LANG_KEY] = DEFAULT_LANG


def t(key: str, **kwargs: object) -> str:
    """Return the translation for ``key`` in the current session language.

    Falls back to English, then to the key itself if missing from all
    dictionaries. Extra keyword arguments are ``.format()``-applied so
    messages like ``"Importing {name}..."`` are parameterised cleanly.
    """
    lang: str = st.session_state.get(LANG_KEY, DEFAULT_LANG)
    for cand in (lang, "en"):
        dict_ = _dicts.get(cand, {})
        if key in dict_:
            value = dict_[key]
            try:
                return value.format(**kwargs) if kwargs else value
            except (KeyError, IndexError):
                # Bad caller — return raw template so nothing silently breaks.
                return value
    return key
