"""Unified LLM client for OpenAI-compatible providers.

PawPilot supports DeepSeek and Qwen via their OpenAI-compatible endpoints, plus a
SiliconFlow-hosted DeepSeek mirror. A single client factory chooses the right endpoint
and model from settings. This keeps the rest of the code provider-agnostic.
"""

from __future__ import annotations

import asyncio

from openai import AsyncOpenAI, OpenAI

from app.core.config import get_settings

# AsyncOpenAI owns an httpx connection pool, so creating one per call throws away
# keep-alive on every request. We cache one client per (event loop, provider) —
# keyed by loop so that a client is never shared across loops, which httpx forbids.
_async_clients: dict[tuple[int, str], AsyncOpenAI] = {}


def current_loop_id() -> int:
    """Identify the running event loop (0 when called outside a loop)."""
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return 0


def get_async_client(provider: str) -> AsyncOpenAI:
    """Return an async OpenAI client configured for the chosen provider.

    Clients are cached per event loop so connections are reused across requests.
    Uses explicit timeouts and retries so that a single slow/hung provider
    request does not block the application indefinitely.

    For the "deepseek" provider, if the native DeepSeek key is absent and a
    SiliconFlow key exists, we transparently use SiliconFlow's DeepSeek mirror
    so the project can run on a single SiliconFlow key.
    """
    key = (current_loop_id(), provider)
    cached = _async_clients.get(key)
    if cached is not None:
        return cached

    settings = get_settings()
    base_url, api_key, _model = _resolve_endpoint(provider)
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )
    _async_clients[key] = client
    return client


def close_async_clients() -> None:
    """Drop cached clients (connections are released when the loop closes)."""
    _async_clients.clear()


def get_sync_client(provider: str) -> OpenAI:
    """Return a sync OpenAI client configured for the chosen provider."""
    settings = get_settings()
    base_url, api_key, model = _resolve_endpoint(provider)
    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


def resolve_model(provider: str) -> str:
    """Return the concrete model id for the active endpoint."""
    _base_url, _api_key, model = _resolve_endpoint(provider)
    return model


def _resolve_endpoint(provider: str) -> tuple[str, str, str]:
    """Resolve (base_url, api_key, model) honoring fallbacks.

    The "deepseek" provider falls back to SiliconFlow-hosted DeepSeek when the
    native key is missing. This keeps demo/CI scenarios working with only a
    SiliconFlow key.
    """
    settings = get_settings()
    if provider == "deepseek":
        if settings.deepseek_api_key:
            return (
                settings.deepseek_base_url,
                settings.deepseek_api_key,
                settings.deepseek_model,
            )
        if settings.siliconflow_api_key:
            return (
                settings.siliconflow_base_url,
                settings.siliconflow_api_key,
                settings.siliconflow_deepseek_model,
            )
        # Allow explicit native config fallback via provider_config so that
        # the missing-key error message remains consistent.
        cfg = settings.provider_config(provider)
        return cfg["base_url"], cfg["api_key"], cfg["model"]

    cfg = settings.provider_config(provider)
    return cfg["base_url"], cfg["api_key"], cfg["model"]
