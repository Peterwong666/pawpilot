# Deployment Guide

## Local Development

### 1. Start the database

```bash
docker-compose -f docker/docker-compose.yml up -d
```

This starts a PostgreSQL 16 + pgvector container on port `5433`.

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys.
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

Visit `http://localhost:8000/docs` for interactive API documentation.

### 6. Run the Streamlit UI

```bash
uv run streamlit run web/app.py
```

Visit `http://localhost:8501`.

---

## Full Docker Stack

For a fully containerized demo:

```bash
cp .env.example .env
# Fill in API keys.
```

```bash
docker-compose -f docker/docker-compose.full.yml up -d --build
```

> The examples above use the standalone `docker-compose` binary. If your machine
> ships the Compose v2 plugin instead, replace it with `docker compose -f ...` —
> the compose files are compatible with both.

- API: `http://localhost:8000`
- Web UI: `http://localhost:8501`
- Database: `localhost:5433`

### Startup order

`docker-compose.full.yml` orders startup with health-gated `depends_on`:

1. `db` becomes healthy (PostgreSQL ready)
2. `ingest` runs once and loads the knowledge base into pgvector
3. `api` starts after `ingest` completes and retries DB connection on transient DNS races
4. `web` starts after `api` is healthy

### Verifying the stack

```bash
./scripts/docker_smoke_test.sh
```

Or manually:

```bash
docker-compose -f docker/docker-compose.full.yml ps
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/db      # {"status":"ok","chunks":675}
curl -s http://localhost:8000/health/embed   # {"status":"ok","model":"BAAI/bge-m3",...}
```

### Teardown

```bash
docker-compose -f docker/docker-compose.full.yml down       # keep data volume
docker-compose -f docker/docker-compose.full.yml down -v    # also drop pgdata
```

---

## Operational Data Import (Seller Central / Advertising CSVs)

Real seller data can be imported at runtime without rebuilding images:

- **UI**: "Data Upload" tab — upload one or more CSVs, set `account_id` / `marketplace`, import.
- **API**: `POST /api/import-csv` (multipart: `file`, `account_id`, `marketplace`);
  `GET /api/import-csv/types` lists supported report types and recognised headers.

Four report types are auto-detected from column headers with alias matching (e.g.
"Ordered Product Sales" → `revenue_usd`): **sales**, **ads**, **inventory**, **costs**.
Values are cleaned (`$`, `,`, `%`), dates parsed as ISO (`2024-10-01`), SKUs normalised.

Storage semantics:

- Rows land in Postgres `operational_*` tables keyed by
  `(account_id, marketplace, sku, date, data_source)` — re-importing is idempotent (upsert),
  and multiple shops/accounts merge side by side.
- On import and at API startup, `HybridDataStore` overlays imported rows onto the DuckDB
  query layer **per SKU+date**: real numbers win where an import exists, simulated data
  remains everywhere else. All existing tools (diagnose, digest, inventory, profit) pick
  this up with no code change.

Verification after import:

```bash
curl -s -X POST http://localhost:8000/api/diagnose \
  -H "Content-Type: application/json" -d '{"sku":"PP-RT-102"}'
```

---

## CI / CD

GitHub Actions runs three jobs on every push and pull request:

1. **test** — `ruff`, `mypy`, `pytest`
2. **docker-build** — builds the production image and verifies imports
3. **docker-smoke** — starts the full stack and checks `/health`, `/health/db`, `/health/embed`

The `docker-smoke` job requires repository secrets:

- `SILICONFLOW_API_KEY` — required for embedding / rerank
- `DEEPSEEK_API_KEY` — optional; falls back to `SILICONFLOW_API_KEY` if not set

Configure them in **Settings → Secrets and variables → Actions**.

---

## MCP Server Usage

Run the MCP server locally:

```bash
uv run python -m app.mcp_server.server
```

Connect Claude Code, Cursor, or any MCP client to the stdio transport.

Example `claude_desktop_config.json` snippet:

```json
{
  "mcpServers": {
    "pawpilot": {
      "command": "uv",
      "args": ["run", "--", "python", "-m", "app.mcp_server.server"],
      "env": {
        "DEEPSEEK_API_KEY": "...",
        "SILICONFLOW_API_KEY": "..."
      }
    }
  }
}
```
