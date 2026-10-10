"""FastAPI application exposing the three PawPilot scenarios."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.data.csv_import import parse_csv, supported_csv_types
from app.data.history_store import HistoryStore
from app.data.hybrid_store import HybridDataStore
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
    sku: str | list[str] = Field(...)
    days: int = Field(default=90, ge=7, le=365)


class DiagnoseRequest(BaseModel):
    sku: str | list[str] = Field(...)
    days: int = Field(default=14, ge=7, le=60)


class ProductDevRequest(BaseModel):
    product_type: str | list[str] = Field(...)


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


def _request_context(request: Request) -> dict[str, Any]:
    """Extract provider / account / simulated-data preferences from request headers."""
    return {
        "provider": request.headers.get("x-provider", "deepseek"),
        "account_id": request.headers.get("x-account-id", "default"),
        "marketplace": request.headers.get("x-marketplace", "US"),
        "use_simulated": request.headers.get("x-use-simulated", "true").lower() != "false",
    }


@app.post("/api/ask")
async def ask(body: AskRequest, request: Request) -> dict[str, Any]:
    ctx = _request_context(request)
    scenario = PolicyQAScenario(provider=ctx["provider"])
    return await scenario.answer(body.query)


@app.post("/api/listing")
async def listing(body: ListingRequest, request: Request) -> dict[str, Any]:
    ctx = _request_context(request)
    scenario = ListingGenScenario(provider=ctx["provider"])
    return await scenario.generate(body.product_info)


@app.post("/api/reviews")
async def reviews(body: ReviewRequest, request: Request) -> dict[str, Any]:
    ctx = _request_context(request)
    scenario = ReviewAnalysisScenario(
        provider=ctx["provider"],
        account_id=ctx["account_id"],
        marketplace=ctx["marketplace"],
        use_simulated=ctx["use_simulated"],
    )
    return await scenario.analyze(body.sku, days=body.days)


@app.post("/api/digest")
async def digest(request: Request) -> dict[str, Any]:
    """Daily operations digest: portfolio table + deterministic alerts + Chinese summary."""
    ctx = _request_context(request)
    scenario = OpsDailyDigestScenario(
        provider=ctx["provider"],
        account_id=ctx["account_id"],
        marketplace=ctx["marketplace"],
        use_simulated=ctx["use_simulated"],
    )
    return await scenario.generate()


@app.post("/api/diagnose")
async def diagnose(body: DiagnoseRequest, request: Request) -> dict[str, Any]:
    """Attribute a SKU's unit change to traffic/conversion/rating/ads/price (Chinese report)."""
    ctx = _request_context(request)
    scenario = SalesDiagnosisScenario(
        provider=ctx["provider"],
        account_id=ctx["account_id"],
        marketplace=ctx["marketplace"],
        use_simulated=ctx["use_simulated"],
    )
    return await scenario.diagnose(body.sku, days=body.days)


@app.post("/api/product-dev")
async def product_dev(body: ProductDevRequest, request: Request) -> dict[str, Any]:
    """Mine competitor reviews for unmet needs and propose product improvements (Chinese report)."""
    ctx = _request_context(request)
    scenario = ProductDevScenario(
        provider=ctx["provider"],
        account_id=ctx["account_id"],
        marketplace=ctx["marketplace"],
        use_simulated=ctx["use_simulated"],
    )
    return await scenario.analyze(body.product_type)


@app.get("/api/import-csv/types")
async def import_csv_types() -> dict[str, Any]:
    """List supported CSV import types and example headers."""
    return {"types": supported_csv_types()}


@app.get("/api/skus")
async def list_skus(request: Request) -> dict[str, Any]:
    """Return SKUs available for analysis, filtered by account context if provided."""
    ctx = _request_context(request)
    store = HybridDataStore(
        account_id=ctx["account_id"],
        marketplace=ctx["marketplace"],
        use_simulated=ctx["use_simulated"],
    )
    return {"skus": store.list_skus()}


@app.get("/api/product-types")
async def list_product_types() -> dict[str, Any]:
    """Return distinct product types from competitor reviews (for VOC analysis)."""
    store = HybridDataStore()
    df = store.query("SELECT DISTINCT product_type FROM competitor_reviews ORDER BY product_type")
    return {"product_types": df["product_type"].tolist()}


@app.get("/api/accounts")
async def list_accounts() -> dict[str, Any]:
    """Return distinct (account_id, marketplace) pairs that have imported data."""
    store = HybridDataStore()
    return {"accounts": store.list_accounts()}


@app.get("/api/data/overview")
async def data_overview() -> dict[str, Any]:
    """Return per-(account, marketplace, type) summary of imported operational data."""
    store = HybridDataStore()
    return {"overview": store.get_overview()}


@app.delete("/api/data")
async def delete_data(
    account_id: str,
    marketplace: str,
    csv_type: str | None = None,
) -> dict[str, Any]:
    """Delete imported data for a given account/marketplace (optionally by type) and resync."""
    store = HybridDataStore()
    deleted = store.delete_and_resync(account_id, marketplace, csv_type=csv_type)
    return {"deleted": deleted, "account_id": account_id, "marketplace": marketplace}


@app.post("/api/import-csv")
async def import_csv(
    file: UploadFile = File(...),  # noqa: B008
    account_id: str = Form(default="default"),  # noqa: B008
    marketplace: str = Form(default="US"),  # noqa: B008
) -> dict[str, Any]:
    """Upload a Seller Central / Advertising CSV and overlay it onto operational data.

    Supported types: sales, ads, inventory, costs.
    """
    content = await file.read()
    parsed = parse_csv(content, filename=file.filename or "data.csv")
    store = HybridDataStore()
    store.overlay(parsed.csv_type, parsed.df, account_id=account_id, marketplace=marketplace)
    return {
        "csv_type": parsed.csv_type,
        "filename": file.filename,
        "rows_imported": len(parsed.df),
        "warnings": parsed.warnings,
        "detection": {
            "confidence": parsed.detection.confidence,
            "matched_columns": parsed.detection.matched_columns,
            "missing_columns": parsed.detection.missing_columns,
        },
        "account_id": account_id,
        "marketplace": marketplace,
    }


# ---------------------------------------------------------------------------
# Analysis history
# ---------------------------------------------------------------------------
class HistoryRequest(BaseModel):
    scenario: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


@app.get("/api/history")
async def list_history(
    request: Request,
    scenario: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List recent analysis history records for the active account."""
    ctx = _request_context(request)
    store = HistoryStore()
    store.init_schema()
    records = store.list(
        account_id=ctx["account_id"],
        marketplace=ctx["marketplace"],
        scenario=scenario,
        limit=limit,
    )
    return {"history": records}


@app.post("/api/history")
async def add_history(body: HistoryRequest, request: Request) -> dict[str, Any]:
    """Save an analysis result to history."""
    ctx = _request_context(request)
    store = HistoryStore()
    store.init_schema()
    record_id = store.add(
        scenario=body.scenario,
        input_data=body.input_data,
        output_data=body.output_data,
        summary=body.summary,
        account_id=ctx["account_id"],
        marketplace=ctx["marketplace"],
    )
    return {"id": record_id}


if __name__ == "__main__":

    import uvicorn

    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8000, reload=True)
