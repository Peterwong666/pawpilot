# 🐾 PawPilot — Amazon Pet-Supplies Operations Copilot

[![CI](https://github.com/Peterwong666/pawpilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Peterwong666/pawpilot/actions/workflows/ci.yml)

PawPilot is an **enterprise-grade RAG knowledge base + Agent workflow** built for Amazon
cross-border e-commerce operations. It demonstrates the full AI application delivery stack
that FDE job descriptions keep asking for: RAG, vector search, Agent orchestration, MCP,
evaluation, and Docker deployment.

> **Built for a real business domain.** The author has run pet-supplies listings on Amazon US,
> reaching category Top 20 with ~$120K monthly GMV and reducing ACOS from 38% to 26%. PawPilot
> turns that operational knowledge into a reproducible, testable, open-source system.

---

## Why this project exists

Most "RAG demos" stop at a chatbot over a few PDFs. FDE interviews ask for more:

- Can you build the **whole RAG pipeline** (parse → chunk → embed → retrieve → rerank → cite)?
- Can you explain **why** you chose one vector database or agent framework over another?
- Can you prove the system works with **offline evaluation**, not just eyeballing answers?
- Can you expose the same logic as **tools / MCP servers** that other agents can consume?
- Can you ship it as a **Dockerized service** with clear ops runbooks?

PawPilot answers yes to all of them.

---

## What it does

Six agent scenarios for a pet-supplies brand on Amazon US — covering both **product
operations** and **product development**:

1. **Policy & SOP Q&A** — Ask Amazon listing, compliance, review, and account-health
   questions. Answers are grounded in the knowledge base and cite source documents.
2. **Listing Generator + Compliance Check** — Input product facts, generate an English
   Amazon listing, then automatically scan it for prohibited words, unsupported claims, and
   style violations with a hybrid rule + LLM engine.
3. **Review Analysis** — Analyze simulated sales/review/ads data by SKU, summarize themes,
   and recommend actions grounded in company SOPs (Chinese output).
4. **Ops Daily Digest** — One-click portfolio briefing: sales WoW, margin, inventory cover,
   ACOS, and rating alerts with a Chinese executive summary.
5. **Sales Diagnosis** — Attribute a SKU's unit change to ad budget, organic traffic,
   rating decline, conversion drop, or price change (Chinese output).
6. **Product Dev VOC** — Mine competitor reviews for unmet needs and propose product
   improvements with profit context (Chinese output).

All scenarios share the same FastMCP tool layer, so Claude Code / Cursor can call PawPilot
as an external MCP server.

---

## Architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│  Streamlit Demo UI (6 scenario tabs + source citations)              │
├────────────────────────────────────────────────────────────────────┤
│  FastAPI API                                                        │
│  /api/ask          → pure RAG policy Q&A                            │
│  /api/listing      → agent listing + hybrid compliance check        │
│  /api/reviews      → agent review analysis (Chinese)                │
│  /api/digest       → portfolio ops daily digest (Chinese)           │
│  /api/diagnose     → sales anomaly attribution (Chinese)            │
│  /api/product-dev  → competitor VOC product improvement (Chinese)   │
├──────────────────────────┬─────────────────────────────────────────┤
│  Self-built Agent        │  FastMCP Server (10 tools)               │
│  Runtime                 │  search_policies                         │
│  • tool-call loop        │  check_listing_compliance                │
│  • conversation memory   │  query_sales_data                        │
│  • max-iter guard        │  analyze_reviews                         │
│  • timeout & retries     │  get_product_info                        │
│                          │  diagnose_sales_anomaly                  │
│                          │  analyze_profit                          │
│                          │  check_inventory_health                  │
│                          │  mine_competitor_reviews                 │
│                          │  generate_daily_digest                   │
├──────────────────────────┴─────────────────────────────────────────┤
│  RAG Pipeline                                                        │
│  ingestion: Markdown → clean → chunk → embed → pgvector              │
│  retrieval:  vector + keyword → RRF fusion → rerank                  │
│  generation: prompt assembly + citation + JSON mode                  │
├────────────────────────────────────────────────────────────────────┤
│  PostgreSQL + pgvector                                               │
│  DuckDB (simulated sales / reviews / ads / costs / inventory /       │
│           competitor_reviews data)                                   │
└────────────────────────────────────────────────────────────────────┘
```

### Technology choices

| Layer | Choice | Why |
|---|---|---|
| Vector DB | **pgvector** | Single-container Postgres; unified metadata + keyword index. See [ADR-001](docs/adr/001-why-pgvector-not-milvus.md). |
| Agent runtime | **Self-built Python loop** | Demonstrates loop, state, guardrails, MCP reuse. See [ADR-002](docs/adr/002-why-self-built-agent-runtime.md). |
| LLM | **DeepSeek + Qwen** | Cost-effective, OpenAI-compatible, supports bilingual eval. See [ADR-003](docs/adr/003-why-deepseek-plus-qwen.md). |
| Embeddings / Rerank | **SiliconFlow BGE** | `bge-m3` + `bge-reranker-v2-m3`, free tier available. |
| Data | **DuckDB** | In-process analytical DB for simulated operational CSVs. |
| UI | **Streamlit** | Fastest path to a clickable demo without frontend sprawl. |
| Package / CI | **uv + ruff + mypy + pytest + GitHub Actions** | Modern Python engineering workflow. |

---

## Quick start

### 1. Clone and configure

```bash
git clone https://github.com/Peterwong666/pawpilot.git
cd pawpilot
cp .env.example .env
# Edit .env with your DeepSeek / Qwen / SiliconFlow keys.

### 2. Start Postgres + pgvector

```bash
docker-compose -f docker/docker-compose.yml up -d
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Ingest the knowledge base

```bash
uv run python scripts/ingest.py
```

### 5. Run the API

```bash
uv run uvicorn app.api.main:app --reload
```

Open `http://localhost:8000/docs` for the interactive API.

### 6. Run the Streamlit UI

```bash
uv run streamlit run web/app.py
```

Open `http://localhost:8501`.

### Full Docker stack

For a one-command containerized deployment:

```bash
docker-compose -f docker/docker-compose.full.yml up -d --build
```

- API: `http://localhost:8000`
- Web UI: `http://localhost:8501`
- Verify: `./scripts/docker_smoke_test.sh`

The compose file handles startup ordering, health checks, and automatic knowledge-base ingestion. See [`docs/deployment.md`](docs/deployment.md) for details and CI secret configuration.

## Evaluation

PawPilot ships with a built-in evaluation framework:

- **100+ seed QA pairs** across policy Q&A, listing compliance, and review analysis
  ([eval/dataset.jsonl](eval/dataset.jsonl)).
- **Deterministic retrieval metrics**: Recall@k, MRR, nDCG@k.
- **LLM-as-judge generation metrics**: answer accuracy, hallucination score.
- **Comparison experiments**: chunking strategy, retrieval mode, and LLM provider.

Run evaluation:

```bash
uv run python eval/runner.py
```

Sample report output:

```json
{
  "overall": {
    "recall_at_k": 0.87,
    "mrr": 0.78,
    "ndcg_at_k": 0.81,
    "answer_score": 0.84,
    "hallucination_score": 0.08
  }
}
```

> The dataset is intentionally small for the MVP. Expand it by running `uv run python eval/generate_qa.py`
> and adding domain-specific questions from your own operations.

A detailed improvement report covering product-development and operations pain points,
implementation decisions, and before/after metrics is available in
[`docs/fde-improvement-report.md`](docs/fde-improvement-report.md).

---

## MCP server

PawPilot exposes the same tool logic as a FastMCP server.

```bash
uv run python -m app.mcp_server.server
```

Connect from Claude Code / Cursor with:

```json
{
  "mcpServers": {
    "pawpilot": {
      "command": "uv",
      "args": ["run", "--", "python", "-m", "app.mcp_server.server"],
      "env": { "DEEPSEEK_API_KEY": "...", "SILICONFLOW_API_KEY": "..." }
    }
  }
}
```

Then ask:

- *"Search our policy docs for Amazon title length rules."*
- *"Check this listing draft for compliance issues."*
- *"Analyze reviews for SKU PP-HR-203 and recommend actions."*
- *"Generate the daily ops digest."*
- *"Diagnose why PP-RT-102 units dropped."*
- *"Mine competitor reviews for rope toy unmet needs."*

---

## Project structure

```text
.
├── app/
│   ├── agent/            # Tool registry + self-built agent runtime
│   ├── api/              # FastAPI application
│   ├── core/             # Config + LLM clients
│   ├── data/             # Simulated operational data (DuckDB)
│   ├── mcp_server/       # FastMCP server
│   ├── rag/              # Ingestion, retrieval, generation
│   └── scenarios/        # Policy QA / listing / review analysis
├── data/
│   ├── knowledge_base/   # Markdown policies, SOPs, product docs, FAQs
│   └── simulated/        # Generated sales / reviews / ads CSVs
├── docker/               # Docker Compose files
├── docs/
│   ├── adr/              # Architecture Decision Records
│   ├── deployment.md
│   └── ops_sop.md
├── eval/                 # Evaluation dataset, generator, runner
├── tests/                # pytest suite
├── web/                  # Streamlit UI
├── pyproject.toml
└── README.md
```

---

## Badcases and lessons learned

| # | Problem | Root cause | Fix |
|---|---|---|---|
| 1 | Policy answers sometimes missed the specific section. | Hierarchical chunker split long sections at arbitrary boundaries. | Added header-aware chunking + RRF so keyword search can recover the right section. |
| 2 | Compliance checker flagged "antibacterial" correctly but missed "FDA certified". | Prompt asked for a generic scan; model prioritized obvious hits. | Added explicit enumerated rule categories to the compliance prompt. |
| 3 | Agent loop occasionally called tools repeatedly with similar queries. | No short-term memory of prior tool results. | Added conversation memory and a max-iteration guardrail. |

These are documented as real debugging decisions, not afterthoughts.

---

## AI-native development workflow

This project was built with heavy use of **Claude Code / Trae** as the primary development
assistant. Rough breakdown:

- ~70% of code scaffolded or reviewed by AI assistant.
- Human oversight on architecture decisions, prompt design, evaluation criteria, and compliance
  correctness.
- Every module has unit tests; retrieval metrics are deterministic.

The goal is not to hide AI usage but to show how an FDE leverages AI coding tools to deliver
production-shaped code faster — exactly what the JDs ask for.

---

## Roadmap

- [x] Expand evaluation dataset to 100+ pairs.
- [ ] Add SP-API CSV import path for real seller data.
- [ ] Add multi-provider model comparison report in UI.
- [ ] Add Langfuse / OpenTelemetry tracing.
- [x] Chinese-language output for analysis scenarios (ops / diagnosis / VOC / reviews).
- [ ] Trend charts and inventory dashboards in Streamlit.

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Contact

Built by [Peterwong666](https://github.com/Peterwong666) as an FDE portfolio project.
Questions or collaboration ideas are welcome via GitHub Issues.
