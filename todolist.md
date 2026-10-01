# PawPilot 项目执行计划

> **项目定位**：面向 Amazon 跨境宠物用品运营场景的企业级 RAG 知识库 + Agent 工作流开源项目。
> **核心目标**：作为 FDE 岗位求职的技术作品集，覆盖 JD 高频关键词（RAG / 向量库 / 评测 / MCP / Docker 部署 / Agent 编排），并体现生产级交付能力。
> **当前状态**：M1-M6 已完成并通过 CI；M7 起进入「灌库 → 联调 → 评测 → 发布」阶段。

---

## 一、执行原则（稳定性 · 兼容性 · 响应速度）

为了让项目在面试中体现“可稳定交付”而非 Demo 水平，后续所有改动必须遵守以下原则：

| 原则 | 具体做法 |
|---|---|
| **兼容性优先** | 所有外部依赖走 OpenAI-compatible 接口；不绑定单一模型商；配置文件支持多 provider 切换。 |
| **稳定性优先** | 每个外部调用必须有超时、重试、降级；关键路径必须可测试；数据库连接使用连接池。 |
| **响应速度优先** | 检索链路优先走异步 + 批处理；embedding/LLM 调用可缓存；Web UI 提供流式响应与 loading 状态。 |
| **可观测性** | 核心接口记录 latency / token usage / retrieval recall；错误日志带 context，便于 badcase 归因。 |
| **可复现** | 所有数据生成、评测、部署脚本版本化；README 提供一键启动命令。 |

---

## 二、已完成里程碑

### M1：项目骨架与知识库

- [x] **M1.1 项目骨架**
  - [x] `pyproject.toml`：Python 3.12+、uv、ruff、mypy strict、pytest 配置。
  - [x] 目录结构：`app/`、`web/`、`eval/`、`scripts/`、`docker/`、`docs/`、`data/`。
  - [x] `.python-version`、`.gitignore`、`.env.example`、`LICENSE`。
- [x] **M1.2 知识库语料构建**
  - [x] Amazon 政策英文文档：`listing_style_guide.md`、`prohibited_listing_words.md`、`review_policy.md`、`account_health_and_seller_metrics.md`、`pet_supplies_compliance.md`、`fulfillment_and_inventory_basics.md`。
  - [x] 脱敏产品文档：`dog_harness_line.md`、`rope_toy_line.md`、`pet_feeding_bowl_line.md`。
  - [x] SOP 文档：`negative_review_response_sop.md`、`listing_quality_checklist.md`、`review_analysis_workflow.md`。
  - [x] FAQ 文档：`cross_border_operations_faq.md`、`customer_service_faq.md`。
- [x] **M1.3 Ingestion 管道**
  - [x] Markdown 解析器（`app/rag/ingestion/parser.py`）。
  - [x] 三种切分策略：fixed、recursive、hierarchical（`app/rag/ingestion/chunking.py`）。
  - [x] SiliconFlow BGE embedding / rerank 客户端（`app/rag/ingestion/embeddings.py`）。
  - [x] PostgreSQL + pgvector 存储与混合搜索（`app/rag/ingestion/store.py`）。
  - [x] 端到端 pipeline（`app/rag/ingestion/pipeline.py`）。
  - [x] 单元测试：`tests/test_chunking.py`。

### M2：检索与生成

- [x] **M2.1 混合检索链路**
  - [x] 向量检索 + 关键词检索 + RRF 融合 + rerank（`app/rag/retrieval/hybrid.py`）。
- [x] **M2.2 政策问答 API + 引用溯源**
  - [x] FastAPI `/api/ask` 接口（`app/api/main.py`）。
  - [x] 生成结果携带 source chunk 与 doc_id 引用。
- [x] **M2.3 Prompt 版本化**
  - [x] `app/rag/generation/prompts.py`：policy_qa、listing_compliance、review_analysis、listing_generation。

### M3：Agent 与业务数据

- [x] **M3.1 自建 Agent runtime**
  - [x] tool-call loop、conversation memory、max-iteration guard、timeout（`app/agent/runtime.py`）。
- [x] **M3.2 三场景编排**
  - [x] `app/scenarios/policy_qa.py`：纯 RAG 政策问答。
  - [x] `app/scenarios/listing_gen.py`：Listing 生成 + 合规检查。
  - [x] `app/scenarios/review_analysis.py`：销售/评论/广告数据分析 + SOP 建议。
- [x] **M3.3 模拟业务数据**
  - [x] `app/data/simulated.py`：生成 sales / reviews / ads CSV。
  - [x] DuckDB 查询接口。
  - [x] 单元测试：`tests/test_simulated_data.py`。
- [x] **M3.4 FastMCP server**
  - [x] `app/mcp_server/server.py`：暴露 5 个工具（search_policies、check_listing_compliance、query_sales_data、analyze_reviews、get_product_info）。
  - [x] `app/agent/tools.py`：Agent 与 MCP 共享同一工具注册表。

### M4：评测体系

- [x] **M4.1 评测集**
  - [x] `eval/generate_qa.py`：生成 102 条问答对（policy_qa / listing_compliance / review_analysis）。
  - [x] `eval/dataset.jsonl`：已落盘 102 条记录。
- [x] **M4.2 评测 runner**
  - [x] `eval/metrics.py`：纯确定性指标 Recall@k、MRR、nDCG@k。
  - [x] `eval/runner.py`：检索评测 + LLM-as-judge（answer score、hallucination score）。
- [x] **M4.3 三组对比实验**
  - [x] 切分策略对比：fixed vs recursive vs hierarchical。
  - [x] 检索模式对比：vector-only vs keyword-only vs hybrid+RRF+rerank。
  - [x] 模型对比：deepseek vs qwen。
- [x] **M4.4 评测报告**
  - [x] `docs/evaluation_report.md`：指标定义、实验结果、bcdcase 分析。

### M5：UI、文档与部署

- [x] **M5.1 Streamlit UI**
  - [x] `web/app.py`：三场景 tab + source citations。
- [x] **M5.2 Docker Compose 完整化**
  - [x] `docker/docker-compose.yml`：dev 版 Postgres+pgvector。
  - [x] `docker/docker-compose.full.yml`：api + web + db 全栈。
  - [x] `Dockerfile`：统一 API/Web 镜像。
- [x] **M5.3 部署文档 + 运维 SOP**
  - [x] `docs/deployment.md`：一键部署、日志查看、备份策略。
  - [x] `docs/ops_sop.md`：常见问题排查、回滚流程。
- [x] **M5.4 README（交付复盘式）**
  - [x] `README.md`：Why / What / Architecture / Quick Start / Evaluation / Roadmap。
- [x] **M5.5 ADR 架构决策文档**
  - [x] `docs/adr/001-why-pgvector-not-milvus.md`。
  - [x] `docs/adr/002-why-self-built-agent-runtime.md`。
  - [x] `docs/adr/003-why-deepseek-plus-qwen.md`。

### M6：工程化收尾

- [x] **M6.1 GitHub Actions CI**
  - [x] `.github/workflows/ci.yml`：ruff + mypy + pytest。
- [x] **M6.2 测试补齐**
  - [x] `tests/test_chunking.py`。
  - [x] `tests/test_retrieval_metrics.py`。
  - [x] `tests/test_simulated_data.py`。
  - [x] pytest 15 passed。
- [x] **M6.3 代码质量**
  - [x] `ruff check app web eval tests scripts` 全绿。
  - [x] `mypy app` 无错误。
  - [x] `.env.example`、`.gitignore` 收尾。
- [x] **M6.4 评测集扩展**
  - [x] 从 30 条扩展至 102 条 QA 对。

---

## 三、待执行里程碑

### M7：启动数据库并灌入知识库

- [x] M7.1 启动 `docker-compose -f docker/docker-compose.yml up -d`。
- [ ] M7.2 创建 `.env` 并填入 API keys（SiliconFlow 必需；DeepSeek/Qwen 二选一）。
- [ ] M7.3 运行 `uv run python scripts/ingest.py` 完成知识库向量化入库。
- [ ] M7.4 验证 `SELECT count(*) FROM chunks;` 与向量索引状态。
- [ ] M7.5 执行一次样例检索，确认 hybrid search 返回合理结果。

### M8：FastAPI 后端联调

- [ ] M8.1 启动 API：`uv run uvicorn app.api.main:app --reload`。
- [ ] M8.2 用 curl/HTTPie 验证 `/api/ask`：返回 answer + sources。
- [ ] M8.3 验证 `/api/listing`：返回 listing + compliance_result。
- [ ] M8.4 验证 `/api/reviews`：返回 analysis + actions。
- [ ] M8.5 压力测试：连续请求 10 次，记录 P50/P95 延迟。
- [ ] M8.6 错误场景：缺少 key、db 断开、超时，验证返回结构。

### M9：Streamlit UI 联调

- [ ] M9.1 启动 UI：`uv run streamlit run web/app.py`。
- [ ] M9.2 Tab 1「政策问答」：输入问题 → 查看回答与引用。
- [ ] M9.3 Tab 2「Listing 生成」：输入产品事实 → 生成文案 → 查看合规检查结果。
- [ ] M9.4 Tab 3「评论分析」：选择 SKU → 查看主题分析 + 运营建议。
- [ ] M9.5 移动端/不同窗口尺寸下布局检查。

### M10：完整评测运行

- [ ] M10.1 配置评测环境变量（provider、model、retrieval mode）。
- [ ] M10.2 运行 `uv run python eval/runner.py`。
- [ ] M10.3 收集 retrieval metrics（Recall@k / MRR / nDCG@k）。
- [ ] M10.4 收集 LLM-as-judge metrics（answer score / hallucination score）。
- [ ] M10.5 生成 `eval/reports/evaluation_report_YYYYMMDD.md`。
- [ ] M10.6 挑出 Top 5 badcase，归因到数据/检索/提示/模型四层。

### M11：Docker Compose 全栈联调

- [ ] M11.1 构建镜像：`docker-compose -f docker/docker-compose.full.yml build`。
- [ ] M11.2 全栈启动：`docker-compose -f docker/docker-compose.full.yml up -d`。
- [ ] M11.3 容器健康检查：`docker-compose ps` + 日志检查。
- [ ] M11.4 从宿主机访问 API 与 UI，验证三场景可用。
- [ ] M11.5 验证 `.env` 在容器内正确加载。
- [ ] M11.6 停止并清理：`docker-compose -f docker/docker-compose.full.yml down -v`。

### M12：GitHub 发布与收尾

- [ ] M12.1 初始化本地 git 仓库（如尚未初始化）。
- [ ] M12.2 确认 `.gitignore` 已排除附件与敏感文件。
- [ ] M12.3 创建 GitHub 仓库 `Peterwong666/pawpilot`。
- [ ] M12.4 推送代码到 main 分支。
- [ ] M12.5 确认 CI badge 在 README 中正常显示。
- [ ] M12.6 打 tag `v0.1.0`，写 Release Notes。
- [ ] M12.7 将 PawPilot 仓库置顶到 GitHub 个人主页。

---

## 四、非功能性需求专项（专业度提升）

### 4.1 稳定性与错误治理

- [ ] **连接池**：PostgreSQL 使用 `asyncpg` 连接池；配置 `min_size` / `max_size` / `max_inactive_time`。
- [ ] **HTTP 客户端复用**：`httpx.AsyncClient` 全局复用，避免每次请求新建连接。
- [ ] **超时与重试**：
  - [ ] LLM 调用：connect=10s、read=120s、max_retries=3。
  - [ ] embedding 调用：connect=10s、read=60s、max_retries=3。
  - [ ] 数据库查询：connect=10s、read=30s。
- [ ] **降级策略**：
  - [ ] LLM 失败时返回“检索结果摘要 + 请稍后重试”。
  - [ ] rerank 失败时回退到 hybrid+RRF 分数。
  - [ ] 关键词检索失败时回退到纯向量检索。
- [ ] **护栏**：
  - [ ] Agent max iterations = 8（已完成）。
  - [ ] Agent 单步 tool timeout = 60s（已完成）。
  - [ ] API 层输入长度限制（title / question / review_text）。
- [ ] **健康检查**：FastAPI 增加 `/health`、`/health/db`、`/health/embed` 端点。

### 4.2 兼容性与可配置性

- [ ] **多 Provider 无缝切换**：通过环境变量 `DEFAULT_PROVIDER` 控制 deepseek / qwen。
- [ ] **模型别名解析**：`resolve_model()` 支持 provider 默认模型与自定义模型覆盖。
- [ ] **OpenAI-compatible 接口**：所有 LLM/embedding/rerank 客户端统一走 chat.completions / embeddings 标准接口。
- [ ] **配置校验**：Pydantic Settings 校验必填 key 与 URL 格式；启动时给出清晰错误提示。
- [ ] **Docker 兼容性**：同时支持 `docker compose` 与 `docker-compose` 命令（文档已标注）。

### 4.3 响应速度与性能优化

- [ ] **异步全链路**：API、Agent、检索、生成全部使用 async/await。
- [ ] **批处理 embedding**：ingestion 与检索重排阶段批量调用 embedding/rerank。
- [ ] **缓存机制**：
  - [ ] 查询缓存：相同 question 在 TTL 内直接返回缓存结果（可选 Redis / 内存）。
  - [ ] embedding 缓存：对高频 chunk 缓存向量，避免重复编码。
- [ ] **检索优化**：
  - [ ] 向量索引使用 `pgvector` ivfflat / hnsw（根据数据量选择）。
  - [ ] 关键词检索使用 GIN 索引（已完成 tsvector 列）。
- [ ] **流式响应**：API 支持 `stream=true`，UI 逐步显示生成内容。
- [ ] **延迟埋点**：每个请求记录 retrieve_latency、generate_latency、total_latency。

### 4.4 可观测性与可维护性

- [ ] **结构化日志**：使用 `structlog` 或标准 logging，统一输出 JSON / 可读格式。
- [ ] **请求追踪**：为每个请求生成 `request_id`，贯穿 API → Agent → LLM → DB。
- [ ] **成本统计**：记录每次 LLM 调用的 prompt tokens / completion tokens / 预估成本。
- [ ] **监控指标**：暴露 `/metrics`（可选 Prometheus 格式）或定期输出到日志。
- [ ] **BAD CASE 归因模板**：在 `docs/badcase_template.md` 提供固定归因格式。

---

## 五、GitHub 发布前检查清单

- [ ] 代码层面：
  - [ ] `ruff check app web eval tests scripts` 全绿。
  - [ ] `mypy app` 无错误。
  - [ ] `pytest tests -q` 全部通过。
- [ ] 配置层面：
  - [ ] `.env.example` 已包含所有必要变量。
  - [ ] `.gitignore` 已排除 `.env`、附件、缓存、数据产物。
- [ ] 文档层面：
  - [ ] README 完整（架构图、Quick Start、API 示例、评测结果、Roadmap）。
  - [ ] 部署文档与运维 SOP 已验证可执行。
  - [ ] ADR 文档覆盖关键选型。
- [ ] 运行层面：
  - [ ] 本地 `docker-compose up` 可一键启动。
  - [ ] 三场景 API/UI 均可正常运行。
  - [ ] 评测 runner 可复现结果。
- [ ] 隐私层面：
  - [ ] 无真实 API key 提交。
  - [ ] 无脱敏前的真实业务数据提交。
  - [ ] 附件文件（项目说明.txt、FDE岗位求职分析与行动建议.md、项目进度.md）未进入仓库。

---

## 六、面试素材清单（与项目同步产出）

- [ ] 一页纸项目复盘：背景 → 目标 → 架构 → 难点 → 结果 → 经验教训。
- [ ] 三个面试故事：
  - [ ] 完整闭环：从需求到 Docker 部署的 PawPilot 交付过程。
  - [ ] 故障定位：CI/lint/mypy 迭代修复或未来线上 badcase 归因。
  - [ ] 砍范围：MVP 选择三个场景而非全面覆盖的决策过程。
- [ ] Demo 脚本：5 分钟演示 policy_qa / listing_gen / review_analysis。
- [ ] 技术 FAQ：RAG vs 微调、Agent 死循环排查、MCP 价值、幻觉治理、评测方法。
- [ ] 简历更新：将 PawPilot 写入「AI 工程与交付能力」一节，附 GitHub 链接。

---

## 七、近期下一步（立即执行）

1. 用户提供 API keys → 创建 `.env`。
2. 运行 `uv run python scripts/ingest.py` 灌库。
3. 启动 API 与 UI，完成 M8/M9 联调。
4. 运行评测 runner，产出报告。
5. 全栈 Docker 联调。
6. 发布到 `Peterwong666/pawpilot`。
