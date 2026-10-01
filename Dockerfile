FROM python:3.13-slim

WORKDIR /app

# Install uv for fast package installation.
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

# Copy project files and install dependencies.
COPY pyproject.toml .env* ./
RUN uv sync --frozen --no-dev

# Copy application code.
COPY app/ ./app/
COPY web/ ./web/
COPY data/ ./data/
COPY eval/ ./eval/
COPY tests/ ./tests/
COPY docs/ ./docs/

ENV PYTHONPATH=/app
ENV PORT=8000

EXPOSE 8000

CMD ["uv", "run", "--", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
