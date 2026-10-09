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
    "err.backend_down":
        "无法连接 PawPilot API（{url}）。请确认 FastAPI 后端已启动：\n\n"
        "uv run uvicorn app.api.main:app --reload",
    "err.backend_down_short":
        "无法连接 PawPilot API（{url}）。请确认 FastAPI 后端已启动。",

    # Tab 名 -------------------------------------------------------------
    "tab.policy": "政策与 SOP 问答",
    "tab.listing": "Listing 生成与合规",
    "tab.reviews": "评论分析",
    "tab.digest": "运营日报",
    "tab.diagnose": "销量诊断",
    "tab.voc": "产品开发 VOC",
    "tab.upload": "数据上传",

    # Tab 1 — Policy Q&A ------------------------------------------------
    "t1.header": "亚马逊政策与 SOP 问答",
    "t1.query_label": "提问",
    "t1.query_default": "宠物用品 Listing 的标题最大长度是多少？",
    "t1.btn_ask": "提问",
    "t1.spinner": "检索并生成答案中…",
    "t1.answer": "答案",
    "t1.sources": "来源",
    "t1.usage": "调用用量",

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
    "t2.btn_gen": "生成 Listing",
    "t2.spinner": "生成并审核 Listing 中…",
    "t2.result": "结果",
    "t2.tool_calls": "工具调用",

    # Tab 3 — Review Analysis -------------------------------------------
    "t3.header": "评论分析",
    "t3.l_sku": "SKU",
    "t3.l_days": "天数",
    "t3.btn_analyze": "分析",
    "t3.spinner": "分析评论中…",
    "t3.analysis": "分析结果",

    # Tab 4 — Ops Daily Digest ------------------------------------------
    "t4.header": "运营日报",
    "t4.desc": "每日 portfolio 简报：销量环比、利润、库存覆盖、ACOS 与评分预警。",
    "t4.btn_digest": "生成日报",
    "t4.spinner": "生成日报中…",
    "t4.digest_title": "运营日报",

    # Tab 5 — Sales Diagnosis -------------------------------------------
    "t5.header": "销量诊断",
    "t5.l_sku": "SKU",
    "t5.l_days": "天数",
    "t5.btn_diagnose": "诊断",
    "t5.spinner": "正在诊断销量异动…",
    "t5.diagnosis": "诊断结果",

    # Tab 6 — Product Dev VOC -------------------------------------------
    "t6.header": "产品开发 VOC",
    "t6.l_product_type": "产品类型",
    "t6.opt_rope": "绳玩具",
    "t6.opt_harness": "胸背带",
    "t6.opt_feeder": "慢食碗",
    "t6.btn_voc": "分析 VOC",
    "t6.spinner": "挖掘竞品评论中的产品机会…",
    "t6.report": "产品开发报告",

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

    # Streamlit 框架级 UI 覆盖 -----------------------------------------
    "menu.about": "### PawPilot\n亚马逊宠物用品运营 Copilot — RAG + Agent + MCP",
    "menu.get_help": "### 使用说明\n在侧边栏选择界面语言与 LLM 提供方后，从 7 个场景中任选一个开始体验。",
    "menu.report_bug": "### 反馈\n请将问题描述、复现步骤与截图整理后提交到项目仓库。",
}


en: dict[str, str] = {
    "app.title": "🐾 PawPilot — Amazon Pet-Supplies Operations Copilot",
    "app.subtitle": "RAG knowledge base + Agent workflows for cross-border e-commerce operations.",
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
    "err.backend_down":
        "Cannot connect to PawPilot API at {url}. "
        "Please make sure the FastAPI backend is running:\n\n"
        "uv run uvicorn app.api.main:app --reload",
    "err.backend_down_short":
        "Cannot connect to PawPilot API at {url}. "
        "Please make sure the FastAPI backend is running.",

    "tab.policy": "Policy Q&A",
    "tab.listing": "Listing + Compliance",
    "tab.reviews": "Review Analysis",
    "tab.digest": "Ops Daily Digest",
    "tab.diagnose": "Sales Diagnosis",
    "tab.voc": "Product Dev VOC",
    "tab.upload": "Data Upload",

    "t1.header": "Amazon Policy & SOP Q&A",
    "t1.query_label": "Ask a question",
    "t1.query_default": "What is the maximum title length for Pet Supplies listings?",
    "t1.btn_ask": "Ask",
    "t1.spinner": "Retrieving and generating answer...",
    "t1.answer": "Answer",
    "t1.sources": "Sources",
    "t1.usage": "Usage",

    "t2.header": "Listing Generator + Compliance Check",
    "t2.l_sku": "SKU",
    "t2.l_product_type": "Product type",
    "t2.l_dog_weight": "Target dog weight",
    "t2.l_size": "Size",
    "t2.l_color": "Color",
    "t2.l_material": "Material",
    "t2.l_key_feature": "Key feature",
    "t2.l_packaging": "Packaging",
    "t2.btn_gen": "Generate listing",
    "t2.spinner": "Generating and reviewing listing...",
    "t2.result": "Result",
    "t2.tool_calls": "Tool calls",

    "t3.header": "Review Analysis",
    "t3.l_sku": "SKU",
    "t3.l_days": "Days",
    "t3.btn_analyze": "Analyze",
    "t3.spinner": "Analyzing reviews...",
    "t3.analysis": "Analysis",

    "t4.header": "Ops Daily Digest",
    "t4.desc": "Portfolio-level daily briefing: sales WoW, margin, inventory cover, ACOS, and rating alerts.",
    "t4.btn_digest": "Generate digest",
    "t4.spinner": "Generating daily digest...",
    "t4.digest_title": "Daily Digest",

    "t5.header": "Sales Diagnosis",
    "t5.l_sku": "SKU",
    "t5.l_days": "Days",
    "t5.btn_diagnose": "Diagnose",
    "t5.spinner": "Diagnosing sales anomaly...",
    "t5.diagnosis": "Diagnosis",

    "t6.header": "Product Dev VOC",
    "t6.l_product_type": "Product type",
    "t6.opt_rope": "rope toy",
    "t6.opt_harness": "harness",
    "t6.opt_feeder": "feeder bowl",
    "t6.btn_voc": "Analyze VOC",
    "t6.spinner": "Mining competitor reviews for product opportunities...",
    "t6.report": "Product Development Report",

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

    # Streamlit framework UI overrides (menu_items + CSS-hidden Deploy)
    "menu.about": "### PawPilot\nAmazon Pet-Supplies Operations Copilot — RAG + Agent + MCP",
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
