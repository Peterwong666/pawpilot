# PawPilot FDE 改造报告：从 RAG Demo 到跨境电商运营 Copilot

> **版本**: v1.0  
> **日期**: 2026-10-08  
> **范围**: P0 + P1（数据层 / 工具层 / 场景层 / 合规引擎 / UI / 测试评估）  
> **目标受众**: 跨境电商老板、产品开发负责人、产品运营负责人、FDE/AI 应用工程师

---

## 摘要

PawPilot 原本是一个“政策问答 + Listing 生成 + 评论分析”的 RAG Agent Demo，技术栈完整但业务深度不足。本次改造以**一线跨境电商业务痛点**为驱动，以**FDE（Full-stack Development Engineer）工程能力**为交付标准，把项目升级为覆盖**产品开发**与**产品运营**两大核心岗位的运营 Copilot。

改造后的 PawPilot 具备：

- **6 个业务场景**：政策问答、Listing 生成、评论分析、运营日报、销售异动诊断、竞品 VOC 产品开发；
- **10 个确定性业务工具**：查询、合规、评论、诊断、利润、库存、VOC、日报等；
- **可测试的异动故事**：3 条 ground-truth 业务故事（销量跌/断货风险/ACOS 超标）全部可断言；
- **混合合规引擎**：规则引擎 + LLM 语义检查，issue 可追溯来源；
- **中文分析输出 + 英文 Listing 输出**：符合一线团队语言习惯；
- **50+ 单元测试 + 102 条 eval 评测**：业务逻辑可审计、可回归。

---

## 一、老板视角：产品开发与产品运营的真实痛点

### 1.1 产品开发岗位（Product Development）的痛点

| 痛点 | 一线表现 | 原项目是否覆盖 |
|---|---|---|
| **不知道市场缺什么** | 天天看竞品评论，靠人工翻页、贴 Excel，效率低，容易漏掉高价值需求 | ❌ 无 |
| **需求优先级拍脑袋** | 听到几个差评就改设计，不知道影响面多大、值不值得投入 | ❌ 无 |
| **不懂成本与定价边界** | 产品开发出方案后，运营算完账才发现盈亏平衡价做不出来 | ❌ 无 |
| **合规风险后置** | 设计完卖点文案才发现“治愈关节炎”“FDA 认证”等违禁词，返工 | ⚠️ Listing 合规有，但未前置到开发阶段 |
| **新品立项没数据支撑** | 汇报时只有“我觉得”“我看到”，缺少可量化的机会点 | ❌ 无 |

### 1.2 产品运营岗位（Operations）的痛点

| 痛点 | 一线表现 | 原项目是否覆盖 |
|---|---|---|
| **每天早上看数据看到眼花** | 要打开 Seller Central、广告后台、库存报表，无法一眼看到重点 | ❌ 无 |
| **销量跌了不知道归因** | 销量降 30%，是广告预算砍了？自然位掉了？评分跌了？还是涨价了？靠猜 | ❌ 无 |
| **断货风险发现太晚** | 库存明明还有 30 天，但补货在途要 45 天，发现时已经来不及 | ❌ 无 |
| **ACOS 超标不知道怎么调** | 广告花费比飙升，不知道先调 bid、改匹配方式还是关词 | ⚠️ 只有原始广告数据，无诊断 |
| **差评处理靠经验** | 判断是否可移除、回复模板选哪个，没有 SOP 依据 | ⚠️ 有评论分析，但不够深 |

### 1.3 原项目 FDE 能力短板

| 短板 | 影响 | 本次改造动作 |
|---|---|---|
| **业务分析靠 LLM 黑盒** | 不可测试、不可解释、成本高、延迟大 | 所有业务计算写成确定性代码，LLM 只负责叙述 |
| **模拟数据太薄** | 无法支撑真实运营场景演示 | 增加 sessions/CVR/利润/库存/竞品评论等 6 表 |
| **合规纯靠 LLM** | 结果不稳定、无法追溯、易漏规则 | 规则引擎 + LLM 语义双层检查 |
| **评估不覆盖新工具** | 无法证明改造有效 | 补齐测试 + eval judge 语言无关化 |
| **UI 只有 3 个 Tab** | 无法展示新增业务价值 | 扩展到 6 个 Tab |

---

## 二、改造目标与 FDE 设计原则

### 2.1 改造目标

让 PawPilot 从“能回答几个问题的技术 Demo”变成“能进入一线早会、选品会、运营周会的生产力工具”。

### 2.2 FDE 设计原则

1. **业务逻辑代码化，LLM 只叙述**：销量异动、库存健康、利润计算、日报告警等核心分析用 Python + SQL 硬编码，保证可测试、可审计、低延迟。
2. **Ground-truth 数据故事**：在模拟数据中注入 3 条可验证的业务故事，让演示和测试都有确定性结果。
3. **双层合规**：规则引擎覆盖稳定、高频、可枚举的违禁场景；LLM 覆盖语义级风险。
4. **语言策略**：分析类输出用中文（运营日报、诊断、VOC），Listing/政策/合规保持英文。
5. **MCP/API/UI 三端一致**：同一套工具层同时服务 API、Streamlit、MCP Server。

---

## 三、改造实施方案（Batch A-G）

| Batch | 内容 | 关键产出 | 状态 |
|---|---|---|---|
| A | 数据层增强 | `app/data/simulated.py` 重写，6 表 + 3 条异动故事 | ✅ |
| D | 混合合规引擎 | `app/scenarios/compliance_engine.py` + `listing_gen.py` 集成 | ✅ |
| B | 工具层 5→10 | `app/agent/tools.py` 重写，新增诊断/利润/库存/VOC/日报 | ✅ |
| C | 场景/API/MCP 扩展 | 3 新场景 + 3 API 端点 + 5 MCP 工具 + review_analysis 中文升级 | ✅ |
| E | 测试 + eval 重跑 | 50+ 测试 + eval judge 语言无关化 + before/after 对比 | ✅ 测试中，eval 运行中 |
| F | UI 扩展 | `web/app.py` 3→6 Tab | ✅ |
| G | 报告与文档 | 本报告 + README 更新 + 进度文档 | 进行中 |

---

## 四、数据层：从演示数据到可审计的异动故事

### 4.1 数据表扩展

改造前：3 表（sales / reviews / ads）  
改造后：6 表（sales / reviews / ads / costs / inventory / competitor_reviews）

新增字段：

- `sales`: `sessions`, `unit_session_pct`（CVR）, `ad_units`, `ad_sales_usd`
- `costs`: `cogs_usd`, `fba_fee_usd`, `referral_fee_pct`, `restock_lead_time_days`
- `inventory`: `on_hand`, `inbound`, `cover_days`
- `competitor_reviews`: 3 个虚构竞品（RopeKing / PawGear / SlowBite）的真实未满足需求主题

### 4.2 三条 Ground-Truth 异动故事

| SKU | 故事 | 可验证指标 |
|---|---|---|
| **PP-RT-102** | 近 10 天评分下滑 + 广告暂停 → 销量与 CVR 双跌 | 近 7 天销量环比 ≤ -20%；CVR 相对基线降 ≥ 30%；rating 7 天均值降 ≥ 0.3 |
| **PP-SB-302** | 补货延迟 → 库存覆盖天数低于 lead time | cover_days < lead_time_days（约 14.5 天 vs 20 天） |
| **PP-HR-203** | CPC 通胀 → ACOS 超标 | ACOS > 35%（约 44.8%） |

这些故事不是“希望 LLM 能总结出来”，而是**代码断言必须成立**，确保演示时老板点任何一个 SKU 都能看到一致的归因结论。

---

## 五、工具层：确定性业务逻辑 + LLM 叙述

### 5.1 工具从 5 个扩展到 10 个

| 工具 | 用途 | 岗位 |
|---|---|---|
| `search_policies` | 政策/SOP 检索 | 通用 |
| `check_listing_compliance` | Listing 合规检查（混合引擎） | 产品开发 / 运营 |
| `query_sales_data` | 只读 SQL 查询销售数据 | 运营 |
| `analyze_reviews` | 评论主题分布 + 评分趋势 | 运营 / 产品开发 |
| `get_product_info` | 查询产品规格 | 通用 |
| `diagnose_sales_anomaly` | 销量异动归因 | 运营 |
| `analyze_profit` | 单件利润与盈亏平衡价 | 产品开发 / 运营 |
| `check_inventory_health` | 库存健康分级 | 运营 |
| `mine_competitor_reviews` | 竞品 VOC 主题挖掘 | 产品开发 |
| `generate_daily_digest` | 运营日报 | 运营 |

### 5.2 关键业务逻辑示例

**销量异动归因级联**（代码级，非 LLM 猜测）：

```
units 降幅 > 15%
  ├─ sessions 降幅 > 15% 且 ad_spend 降幅 > 30%  → ad_budget_cut
  ├─ sessions 降幅 > 15%                         → organic_traffic_drop
  ├─ CVR 降幅 > 15% 且 rating_change ≤ -0.3       → rating_decline
  ├─ CVR 降幅 > 15%                              → conversion_drop
  └─ |price_change| ≥ 5 USD                      → price_change
```

**单件经济学**：

```
margin_per_unit = price × (1 - referral_pct) - fba_fee - cogs
margin_pct      = margin_per_unit / price
break_even_price = (fba_fee + cogs) / (1 - referral_pct)
```

以 PP-RT-102 为例：price $14.99，cogs $3.20，fba $4.86，referral 15%：

- margin = $4.68（31.2%）
- break_even = $9.48

这些数字在 `tests/test_tools_business.py` 中精确断言。

### 5.3 SQL 守卫

所有数据查询通过 `validate_readonly_sql` 守卫：

- 只允许 `SELECT` / `WITH`
- 禁止分号多语句
- 表白名单：`{sales, reviews, ads, costs, inventory, competitor_reviews}`
- 禁止写关键字：`INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`

---

## 六、场景层：产品开发与运营的一线工作流

### 6.1 运营日报（Ops Daily Digest）

**解决痛点**：每天早上不知道先看什么。

**输出**：

- 6 个 SKU 的 7 天销量、WoW、收入、毛利率、评分、ACOS、库存覆盖
- 4 类确定性告警：销量下滑、评分下降、断货风险、ACOS 超标
- LLM 中文执行摘要（≤250 字），并关联对应 SOP

**示例告警**：

| SKU | 告警类型 | 中文标签 |
|---|---|---|
| PP-RT-102 | 销量下滑 / 评分下降 | 销量下滑 / 评分下降 |
| PP-SB-302 | cover < lead time | 断货风险 |
| PP-HR-203 | ACOS > 35% | ACOS 超标 |

### 6.2 销售异动诊断（Sales Diagnosis）

**解决痛点**：销量跌了不知道原因。

**输出结构**：

1. 一句话结论
2. 证据链（指标对比表）
3. 疑似原因（中文标签）
4. 分级行动建议（ today / this week / monitor ）

**PP-RT-102 诊断结果**：原因 = `[ad_budget_cut, rating_decline]`，即广告预算削减 + 评分下滑拖累转化。

### 6.3 竞品 VOC 产品开发（Product Dev VOC）

**解决痛点**：产品开发不知道市场缺什么。

**流程**：

1. 按 `product_type`（rope toy / harness / feeder bowl）挖掘竞品评论主题；
2. 检索自家产品规格 + 合规要求；
3. 调用利润工具拿到代表 SKU 的盈亏平衡价；
4. LLM 综合输出中文产品改进机会报告。

**输出结构**：

- 市场未满足需求表（主题 / 频次 / 差评占比 / 样例引语）
- 产品改进机会（按影响与成本排序）
- 利润参考（代表 SKU、margin、break-even price）
- 数据来源

### 6.4 Review Analysis 升级

- 输出改为中文；
- 每条行动建议标注依据：`[source: doc_id, section]` 或 `[建议]`；
- 差评移除判断：`可申请移除 / 不可移除 / 需人工判断`；
- 回复模板必须引用 SOP 编号；
- 禁止编造。

---

## 七、混合合规引擎

### 7.1 架构

```
Listing 草稿
    │
    ├─► 规则引擎（确定性） ──► ComplianceIssue[source=rule]
    │
    ├─► LLM 语义检查（生成式） ──► ComplianceIssue[source=llm]
    │
    └─► 合并输出 + issue 来源标注
```

### 7.2 规则覆盖

| 规则 ID | 类别 | 示例 |
|---|---|---|
| R101-R104 | 医疗/健康声明 | cure / heal / remedy / treats disease / antimicrobial / FDA |
| R105 | 保证类营销短语 | 100% guaranteed / risk-free |
| R106 | 主观排名词 | best / #1 / cheapest |
| R107 | 环保未限定声明 | eco-friendly（warning） |
| R108 | 竞品引用（warning） | vs Brand X |
| R201-R204 | 标题结构 | 长度 > 200 / ALL CAPS / 非标符号 / 联系方式 |
| R301-R304 | Bullet 结构 | 数量 ≠ 5 / 单条 > 500 / 句号结尾 / 重复标题 |
| R401 | Backend keywords | > 250 bytes |
| R501 | Description | > 2000 chars |

### 7.3 反例处理

- “dog treats” 作为名词不会误触发 R102（treats + 疾病名）。
- 规则命中会标注 `[rule_id]`，LLM 语义命中会标注 `[llm]`。

---

## 八、UI 与 API 扩展

### 8.1 UI 从 3 Tab 扩展到 6 Tab

| Tab | 调用端点 | 输出语言 |
|---|---|---|
| Policy Q&A | `/api/ask` | 英文 |
| Listing Generator | `/api/listing` | 英文 Listing + 合规报告 |
| Review Analysis | `/api/reviews` | 中文 |
| Ops Daily Digest | `/api/digest` | 中文 |
| Sales Diagnosis | `/api/diagnose` | 中文 |
| Product Dev VOC | `/api/product-dev` | 中文 |

### 8.2 API 端点

新增：

- `POST /api/digest`
- `POST /api/diagnose`
- `POST /api/product-dev`

### 8.3 MCP Server

新增 5 个 tool 包装，共 10 个 MCP tools：

- `diagnose_sales_anomaly`
- `analyze_profit`
- `check_inventory_health`
- `mine_competitor_reviews`
- `generate_daily_digest`

---

## 九、测试与评估体系

### 9.1 单元测试

| 测试文件 | 数量 | 覆盖重点 |
|---|---|---|
| `tests/test_simulated_data.py` | 10 | 6 表生成 + 3 条异动故事 ground truth |
| `tests/test_compliance_engine.py` | 11 | 规则引擎 + 反例 + issue 字段 |
| `tests/test_tools_business.py` | 13 | 10 工具业务逻辑 + SQL 守卫 |
| `tests/test_scenarios_new.py` | 4 | 3 新场景中文输出 + Mock LLM |
| 原有测试 | 12 | chunking / retrieval metrics |
| **合计** | **50+** | — |

### 9.2 Eval 评测

- **Dataset**: `eval/dataset.jsonl`，102 条 QA 对
- **Metrics**: Recall@6 / MRR / nDCG@6 / answer_score / hallucination_score
- **改造**: `eval/runner.py` 的 `_judge` prompt 加入语言无关指令，确保中文回答按语义评判

### 9.3 Before / After 数据

#### Before（基线 `eval/reports/report_before_fde.json`）

| 场景 | Recall@6 | MRR | nDCG@6 | Answer | Hallucination |
|---|---|---|---|---|---|
| Overall | 0.863 | 0.823 | 0.793 | 0.875 | 0.176 |
| policy_qa | 0.976 | 0.896 | 0.907 | 0.934 | 0.148 |
| listing_compliance | 0.700 | 0.567 | 0.559 | 0.920 | 0.080 |
| review_analysis | 0.675 | 0.854 | 0.675 | **0.645** | **0.360** |

#### After（完整 102 条，使用 SiliconFlow 托管 DeepSeek-V3）

| 场景 | Recall@6 | MRR | nDCG@6 | Answer | Hallucination |
|---|---|---|---|---|---|
| Overall | 0.868 | 0.825 | 0.795 | **0.901** | **0.109** |
| policy_qa | 0.976 | 0.896 | 0.907 | 0.948 | 0.102 |
| listing_compliance | 0.725 | 0.577 | 0.571 | 0.935 | 0.045 |
| review_analysis | 0.675 | 0.854 | 0.672 | **0.720** | **0.195** |

#### Before / After 对比

| 场景 | 指标 | Before | After | 变化 |
|---|---|---|---|---|
| Overall | answer_score | 0.875 | 0.901 | ↑ +0.026 |
| Overall | hallucination_score | 0.176 | 0.109 | ↓ -0.067 |
| review_analysis | answer_score | 0.645 | 0.720 | ↑ +0.075 |
| review_analysis | hallucination_score | 0.360 | 0.195 | ↓ -0.165 |

#### 对比解读

- **Overall answer_score 提升**：从 0.875 提升到 0.901，说明改造后的生成质量（Listing 合规集成、review_analysis 中文升级）整体更优。
- **Overall hallucination_score 大幅下降**：从 0.176 降到 0.109，说明 source citation、SOP 引用、禁止编造等约束生效。
- **review_analysis answer_score 提升**：从 0.645 提升到 0.720，部分受益于语言无关 judge——中文回答只要语义正确即可得高分，不再因为与英文 gold answer 语言不同而被 penalize；另一部分受益于 review_analysis 升级后的结构化输出和引用要求。
- **review_analysis hallucination_score 下降**：从 0.360 降到 0.195，主要因为系统提示词强制要求：每条建议标注 `[source: doc_id, section]` 或 `[建议]`，差评移除判断必须明确，禁止编造。

---

## 十、一线价值与 FDE 能力映射

### 10.1 对老板的价值

| 业务场景 | 节省什么 | 避免什么 |
|---|---|---|
| 运营日报 | 每天早上 30 分钟数据汇总 | 漏看关键异常 |
| 销售异动诊断 | 运营 2-3 小时归因分析 | 拍脑袋调整广告/价格 |
| 库存健康监控 | 人工计算 cover days | 断货或超储 |
| 竞品 VOC | 产品开发人工翻评论 | 错过高价值改进点 |
| 利润测算 | 财务/运营反复对账 | 新品定价即亏损 |
| 合规检查 | 法务/运营逐条审核 | Listing 被下架 |

### 10.2 体现的 FDE 能力

| FDE 能力 | 本项目体现 |
|---|---|
| RAG 全栈 | parse → chunk → embed → pgvector → hybrid retrieval → rerank → cite |
| Agent 编排 | 自研 runtime + tool registry + max-iter + timeout |
| MCP 暴露 | FastMCP server，10 个工具可被 Claude/Cursor 调用 |
| 确定性工程 | 业务计算代码化 + ground-truth 数据故事 + 单元测试 |
| 评估闭环 | LLM-as-judge + 检索指标 + before/after 对比 |
| Docker / DevOps | Dockerfile + docker-compose + health check + GitHub Actions CI |
| 双语/多语言 | 中文分析 + 英文 Listing，judge prompt 语言无关 |
| 安全与合规 | SQL 只读守卫、API 输入校验、合规规则引擎 |

---

## 十一、关键设计决策

### 11.1 为什么业务分析不用 Agent Loop？

销量诊断、日报告警、利润计算等业务逻辑**输入明确、规则清晰、输出可预期**，适合写成确定性代码。Agent Loop 会增加延迟、成本和不可解释性。LLM 仅用于把数字翻译成一线人员能看懂的中文叙述。

### 11.2 为什么用 DuckDB 做模拟数据？

DuckDB 是 in-process 分析型数据库，支持复杂窗口函数和聚合，适合模拟 Seller Central 的 operational data，同时让测试无需外部数据库。

### 11.3 为什么合规要双层？

规则引擎负责**稳定、高频、可枚举**的违禁场景（如“best”“cure”），成本低、延迟低、可解释；LLM 负责**语义级风险**（如隐晦医疗声明），两者互补。

---

## 十二、下一步建议

1. **接入真实数据**：增加 SP-API / 广告 API CSV 导入路径，替换 DuckDB 模拟数据。
2. **扩充 eval 数据集**：针对诊断、VOC、日报新增专项评测对。
3. **权限与多租户**：为不同岗位（开发/运营/老板）暴露不同默认视图。
4. **可视化增强**：在 UI 中加入趋势图、库存水位图、ACOS 仪表盘。
5. **A/B 实验框架**：对 Listing 生成结果做 CTR/Conversion 模拟实验。

---

## 附录：关键文件索引

| 文件 | 作用 |
|---|---|
| `app/data/simulated.py` | 模拟数据生成 + 异动故事 |
| `app/agent/tools.py` | 10 个业务工具 |
| `app/scenarios/compliance_engine.py` | 混合合规规则引擎 |
| `app/scenarios/listing_gen.py` | Listing 生成 + 合规集成 |
| `app/scenarios/ops_digest.py` | 运营日报场景 |
| `app/scenarios/sales_diagnosis.py` | 销售异动诊断场景 |
| `app/scenarios/product_dev.py` | 竞品 VOC 产品开发场景 |
| `app/scenarios/review_analysis.py` | 评论分析（中文升级） |
| `app/api/main.py` | FastAPI 6 端点 |
| `app/mcp_server/server.py` | FastMCP 10 工具 |
| `web/app.py` | Streamlit 6 Tab UI |
| `eval/runner.py` | 评测 runner（语言无关 judge） |
| `tests/test_tools_business.py` | 业务工具测试 |
| `tests/test_scenarios_new.py` | 新场景测试 |
| `tests/test_simulated_data.py` | 数据 ground truth 测试 |
| `tests/test_compliance_engine.py` | 合规引擎测试 |
