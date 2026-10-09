"""FastAPI application exposing the three PawPilot scenarios."""

from __future__ import annotations

import asyncio
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
from app.rag.ingestion.store import ChunkStore, close_pools
from app.scenarios.listing_gen import ListingGenScenario
from app.scenarios.ops_digest import OpsDailyDigestScenario
from app.scenarios.policy_qa import PolicyQAScenario
from app.scenarios.product_dev import ProductDevScenario
from app.scenarios.review_analysis import ReviewAnalysisScenario
from app.scenarios.sales_diagnosis import SalesDiagnosisScenario

logger = logging.getLogger(__name__)

# Input size guardrails (characters). These protect against accidental abuse
# and keep LLM context windows predictable.
MAX_QUERY_LENGTH = 2000
MAX_PRODUCT_INFO_KEYS = 50
MAX_PRODUCT_INFO_VALUE_LENGTH = 2000


async def _wait_for_db(max_retries: int = 10, base_delay: float = 1.0) -> None:
    """Wait for PostgreSQL to be reachable with exponential backoff.

    In containerized environments the database host may not be resolvable
    immediately even after the service reports healthy. A failed connection
    attempt may leave a stale pool behind, so we close pools before retrying
    to force a fresh DNS lookup and connection.
    """
    for attempt in range(1, max_retries + 1):
        try:
            ChunkStore().init_schema()
            return
        except Exception as exc:
            logger.warning(
                "Database not ready (attempt %d/%d): %s",
                attempt,
                max_retries,
                exc,
            )
            close_pools()
            if attempt == max_retries:
                raise
            await asyncio.sleep(base_delay * (2 ** (attempt - 1)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate required configuration and schema on startup.
    settings = get_settings()
    settings.validate_runtime()
    await _wait_for_db()
    yield
    # Release pooled database connections on shutdown.
    close_pools()


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


class DiagnoseRequest(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    days: int = Field(default=14, ge=7, le=60)


class ProductDevRequest(BaseModel):
    product_type: str = Field(..., min_length=3, max_length=64)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
async def health_db() -> dict[str, Any]:
    """Check PostgreSQL connectivity."""
    return {"status": "ok", "chunks": ChunkStore().count_chunks()}


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


@app.post("/api/digest")
async def digest() -> dict[str, Any]:
    """Daily operations digest: portfolio table + deterministic alerts + Chinese summary."""
    scenario = OpsDailyDigestScenario()
    return await scenario.generate()


@app.post("/api/diagnose")
async def diagnose(body: DiagnoseRequest) -> dict[str, Any]:
    """Attribute a SKU's unit change to traffic/conversion/rating/ads/price (Chinese report)."""
    scenario = SalesDiagnosisScenario()
    return await scenario.diagnose(body.sku, days=body.days)


@app.post("/api/product-dev")
async def product_dev(body: ProductDevRequest) -> dict[str, Any]:
    """Mine competitor reviews for unmet needs and propose product improvements (Chinese report)."""
    scenario = ProductDevScenario()
    return await scenario.analyze(body.product_type)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=True)
