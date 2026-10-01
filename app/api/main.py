"""FastAPI application exposing the three PawPilot scenarios."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.rag.ingestion.embeddings import EmbeddingClient
from app.rag.ingestion.store import ChunkStore
from app.scenarios.listing_gen import ListingGenScenario
from app.scenarios.policy_qa import PolicyQAScenario
from app.scenarios.review_analysis import ReviewAnalysisScenario

logger = logging.getLogger(__name__)

# Input size guardrails (characters). These protect against accidental abuse
# and keep LLM context windows predictable.
MAX_QUERY_LENGTH = 2000
MAX_PRODUCT_INFO_KEYS = 50
MAX_PRODUCT_INFO_VALUE_LENGTH = 2000


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate required configuration and schema on startup.
    settings = get_settings()
    settings.validate_runtime()
    ChunkStore().init_schema()
    yield


app = FastAPI(
    title="PawPilot API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_tracing(request: Request, call_next):
    """Attach request_id and response-time headers to every request."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4())[:12])
    request.state.request_id = request_id
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled exception", extra={"request_id": request_id})
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["x-request-id"] = request_id
    response.headers["x-response-time-ms"] = f"{elapsed_ms:.2f}"
    logger.info(
        "%s %s %s - %.2fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        extra={"request_id": request_id},
    )
    return response


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_LENGTH)


class ListingRequest(BaseModel):
    product_info: dict[str, Any]

    @field_validator("product_info")
    @classmethod
    def _validate_product_info(cls, data: dict[str, Any]) -> dict[str, Any]:
        if len(data) > MAX_PRODUCT_INFO_KEYS:
            raise ValueError(f"product_info may contain at most {MAX_PRODUCT_INFO_KEYS} keys")
        for key, value in data.items():
            if isinstance(value, str) and len(value) > MAX_PRODUCT_INFO_VALUE_LENGTH:
                raise ValueError(
                    f"product_info['{key}'] exceeds {MAX_PRODUCT_INFO_VALUE_LENGTH} characters"
                )
        return data


class ReviewRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    days: int = Field(default=90, ge=7, le=365)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, Any]:
    """Check PostgreSQL connectivity."""
    store = ChunkStore()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks;")
            row = cur.fetchone()
            count = row[0] if row else 0
    return {"status": "ok", "chunks": count}


@app.get("/health/embed")
async def health_embed() -> dict[str, Any]:
    """Check embedding client configuration without making a paid call."""
    client = EmbeddingClient()
    return {
        "status": "ok",
        "model": client.model,
        "dim": client.dim,
        "base_url": get_settings().siliconflow_base_url,
    }


@app.post("/api/ask")
async def ask(body: AskRequest) -> dict[str, Any]:
    scenario = PolicyQAScenario()
    return await scenario.answer(body.query)


@app.post("/api/listing")
async def listing(body: ListingRequest) -> dict[str, Any]:
    scenario = ListingGenScenario()
    return await scenario.generate(body.product_info)


@app.post("/api/reviews")
async def reviews(body: ReviewRequest) -> dict[str, Any]:
    scenario = ReviewAnalysisScenario()
    return await scenario.analyze(body.sku, days=body.days)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=True)
