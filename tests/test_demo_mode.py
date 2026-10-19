"""Demo mode (PAWPILOT_DEMO_MODE=1) tests — hermetic: no network, DB or real keys.

Proves the zero-cost offline path: with every key unset, validate_runtime skips
its checks, the bundled corpus ingests into the in-memory store (idempotently),
and the API serves a full Q&A loop.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from app.api.main import app
from app.core.config import Settings, get_settings
from app.rag.retrieval.demo import DemoChunkStore, DemoRetriever
from scripts.ingest import app as ingest_app

_KEY_VARS = ("SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY")


def _settings(**overrides: object) -> Settings:
    """Build a Settings hermetically: explicit kwargs beat env vars and .env."""
    base: dict[str, object] = dict.fromkeys(
        ("siliconflow_api_key", "deepseek_api_key", "dashscope_api_key"), ""
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_validate_runtime_skips_checks_in_demo_mode(capsys: pytest.CaptureFixture) -> None:
    """No keys and a non-Postgres DSN must not raise when demo mode is on."""
    _settings(demo_mode=True, database_url="duckdb://demo").validate_runtime()
    assert "DEMO MODE" in capsys.readouterr().out


def test_validate_runtime_still_fails_fast_when_demo_mode_off() -> None:
    """The batch-1 fail-fast contract is unchanged with demo mode off (default)."""
    with pytest.raises(ValueError, match="SILICONFLOW_API_KEY"):
        _settings().validate_runtime()


async def test_demo_retriever_ingest_idempotent_and_retrieves() -> None:
    store = DemoChunkStore()  # fresh in-memory store keeps the test isolated
    retriever = DemoRetriever(store=store)
    count = await retriever.ensure_ingested()
    assert count > 0
    # Second call is a no-op (idempotent).
    assert await retriever.ensure_ingested() == count

    chunks = await retriever.retrieve_texts("listing 标题最多多少字符？")
    assert chunks, "demo corpus should answer a listing-title question"
    assert all("text" in chunk and "doc_id" in chunk for chunk in chunks)


def test_demo_api_full_qa_loop_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Boot the API with zero keys via demo mode and complete a Q&A round-trip."""
    monkeypatch.setenv("PAWPILOT_DEMO_MODE", "1")
    for var in _KEY_VARS:
        monkeypatch.setenv(var, "")  # env vars override any local .env values
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            health = client.get("/health/db")
            assert health.status_code == 200
            assert health.json()["status"] == "demo"
            assert health.json()["chunks"] > 0

            resp = client.post("/api/ask", json={"query": "listing 标题最长多少字符？"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["provider"] == "demo"
            assert data["answer"]
            assert data["sources"], "answer must cite demo corpus chunks"

            # Auxiliary endpoints the Streamlit UI polls must not error either.
            assert client.get("/api/skus").json()["skus"], "simulated SKUs expected"
            assert client.get("/api/accounts").json() == {"accounts": []}
            assert client.get("/api/history").json() == {"history": []}
    finally:
        get_settings.cache_clear()


def test_ingest_cli_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ingest CLI ingests the bundled demo corpus instead of requiring keys."""
    monkeypatch.setenv("PAWPILOT_DEMO_MODE", "1")
    for var in _KEY_VARS:
        monkeypatch.setenv(var, "")
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(ingest_app, [])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 0
    assert "Demo mode" in result.output
