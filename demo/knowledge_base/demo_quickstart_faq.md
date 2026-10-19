# PawPilot Demo 模式快速 FAQ

## Demo 模式是什么

Demo 模式（PAWPILOT_DEMO_MODE=1）是零成本体验路径：不需要任何 API key，
不需要 Docker 或 PostgreSQL，启动后自动把本目录的示例知识库入库到本地
DuckDB 内存库，用确定性本地 embedding 完成检索，由演示生成器输出回答。

## 可以体验哪些场景

- 政策与 SOP 问答：对示例知识库的完整 RAG 检索问答（本地向量 + 关键词 RRF 融合）。
- Listing 生成与合规检查：演示生成器产出 Listing，合规规则引擎（真实代码）照常工作。
- 运营日报 / 销量诊断 / 产品开发 VOC：确定性分析层使用内置模拟 SKU 数据，演示生成器负责叙述。
- 评论分析场景依赖 LLM Agent 运行时，Demo 模式下会返回说明提示。

## 如何切换到完整模式

1. 申请一个 SiliconFlow API key（免费额度覆盖 embedding 与 rerank）。
2. 在 .env 中填入 SILICONFLOW_API_KEY，并设置 PAWPILOT_DEMO_MODE=0（或删除该变量）。
3. 启动 PostgreSQL + pgvector，运行 scripts/ingest.py 入库完整知识库。

## 数据说明

Demo 模式的所有数据均为内置示例：知识库是真实语料的简化版，运营数据来自
程序生成的模拟 SKU 组合，不涉及任何真实店铺信息；进程重启后内存数据自动重建。
