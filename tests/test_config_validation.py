"""Fail-fast configuration validation tests (hermetic: no network, DB or real keys).

Guards the startup contract: when required keys are missing, every entrypoint
must raise/print actionable guidance (which key, where to apply, free tier) and
must never fall through to the OpenAI SDK's misleading OPENAI_API_KEY error.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from app.core.config import SILICONFLOW_CONSOLE_URL, Settings, get_settings
from scripts.ingest import app as ingest_app

_KEY_VARS = ("SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY")


def _settings(**overrides: str) -> Settings:
    """Build a Settings hermetically: explicit kwargs beat env vars and .env."""
    base = dict.fromkeys(
        ("siliconflow_api_key", "deepseek_api_key", "dashscope_api_key"), ""
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_validate_runtime_fails_fast_without_any_key() -> None:
    with pytest.raises(ValueError) as excinfo:
        _settings().validate_runtime()
    message = str(excinfo.value)
    # Guidance: which key is missing, where to apply, free-tier note.
    assert "SILICONFLOW_API_KEY" in message
    assert SILICONFLOW_CONSOLE_URL in message
    assert "free" in message.lower()
    # Never leak the OpenAI SDK's misleading default variable name.
    assert "OPENAI_API_KEY" not in message


def test_validate_runtime_single_siliconflow_key_covers_full_pipeline() -> None:
    """One SiliconFlow key must pass validation: embedding + rerank + generation mirror."""
    _settings(siliconflow_api_key="sk-test").validate_runtime()  # must not raise


def test_validate_runtime_deepseek_only_still_requires_siliconflow() -> None:
    with pytest.raises(ValueError) as excinfo:
        _settings(deepseek_api_key="sk-test").validate_runtime()
    message = str(excinfo.value)
    assert "SILICONFLOW_API_KEY" in message
    assert SILICONFLOW_CONSOLE_URL in message
    assert "OPENAI_API_KEY" not in message


def test_validate_runtime_rejects_bad_database_url() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        _settings(siliconflow_api_key="sk-test", database_url="sqlite://x").validate_runtime()


def test_ingest_cli_fails_fast_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """scripts/ingest.py must exit 1 with friendly guidance, not an SDK traceback."""
    for var in _KEY_VARS:
        monkeypatch.setenv(var, "")  # env vars override any local .env values
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(ingest_app, [])
    finally:
        get_settings.cache_clear()
    assert result.exit_code == 1
    output = result.output
    assert "SILICONFLOW_API_KEY" in output
    assert SILICONFLOW_CONSOLE_URL in output
    assert "free" in output.lower()
    assert "OPENAI_API_KEY" not in output
