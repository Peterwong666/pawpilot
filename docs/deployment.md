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
# Fill in API keys.```bash
docker-compose -f docker/docker-compose.full.yml up -d --build
```

- API: `http://localhost:8000`
- Web UI: `http://localhost:8501`
- Database: `localhost:5433`

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
