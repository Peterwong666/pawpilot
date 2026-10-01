# Operations SOP — PawPilot Self-Hosted Instance

## Backup

### Database

```bash
docker exec pawpilot-db pg_dump -U pawpilot -d pawpilot > pawpilot_$(date +%F).sql
```

Store the dump in version-controlled or encrypted cloud storage. Restore with:

```bash
docker exec -i pawpilot-db psql -U pawpilot -d pawpilot < pawpilot_YYYY-MM-DD.sql
```

### Knowledge base source files

Source Markdown files live in `data/knowledge_base/`. They are already under version control;
the vector index is a derived artifact and can be rebuilt with `scripts/ingest.py`.

## Upgrade

1. Pull the latest code.
2. Rebuild the Docker image: `docker compose -f docker/docker-compose.full.yml build`.
3. If the ingestion pipeline changed, re-run ingestion inside the container or locally.
4. Restart services.

## Rebuild the vector index

```bash
uv run python scripts/ingest.py --reset
```

Use `--reset` only when you want to replace the existing index.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `pgvector` extension missing | Wrong Postgres image | Use `pgvector/pgvector:pg16` |
| API returns empty answers | Knowledge base not ingested | Run `scripts/ingest.py` |
| Streamlit cannot connect | Missing `DATABASE_URL` | Check `.env` and restart |
| LLM calls fail | Missing API key | Verify `.env` keys and provider base URLs |
| Slow retrieval | Too few ivfflat lists or large corpus | Tune `lists` in `store.py` or increase `RETRIEVAL_TOP_K` |

## Security

- Never commit `.env` files to version control.
- Rotate API keys every 90 days.
- Expose the database port (`5433`) only on localhost in production.
