FROM python:3.13-slim

WORKDIR /app

# Install uv for fast package installation.
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

# Copy dependency manifests and install dependencies (reproducible via uv.lock).
# The project itself is NOT installed into site-packages: PYTHONPATH=/app imports it
# directly, which keeps this layer cached across code changes.
# Secrets are NOT baked into the image; they are injected at runtime (env_file / env).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code.
COPY app/ ./app/
COPY web/ ./web/
COPY data/ ./data/
COPY eval/ ./eval/
COPY tests/ ./tests/
COPY docs/ ./docs/

ENV PYTHONPATH=/app
ENV PORT=8000
# Never re-resolve dependencies at runtime; the image is already synced from uv.lock.
ENV UV_NO_SYNC=1

EXPOSE 8000

CMD ["uv", "run", "--", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
