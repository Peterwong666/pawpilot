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

### Verifying the stack

```bash
docker-compose -f docker/docker-compose.full.yml ps
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/db      # {"status":"ok","chunks":135}
```

`docker-compose.full.yml` orders startup with health-gated `depends_on`:
`db` → `api` (healthchecked on `/health`) → `web`. The `web` container receives
`PAWPILOT_API_URL=http://api:8000` so it talks to the API over the compose network.

### Teardown

```bash
docker-compose -f docker/docker-compose.full.yml down       # keep data volume
docker-compose -f docker/docker-compose.full.yml down -v    # also drop pgdata
```

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
