"""Central configuration via pydantic-settings.

All runtime knobs (API keys, model names, RAG tuning, guardrails) live here so
that every module reads one source of truth. Values are loaded from the
environment or a local `.env` file; see `.env.example`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Supported LLM providers (both OpenAI-protocol compatible).
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_QWEN = "qwen"
SUPPORTED_PROVIDERS = {PROVIDER_DEEPSEEK, PROVIDER_QWEN}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Default provider ---
    default_provider: str = PROVIDER_DEEPSEEK

    # --- LLM providers ---
    # --- DeepSeek (native or SiliconFlow-hosted) ---
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # --- Qwen via DashScope ---
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"

    # --- SiliconFlow (embedding / rerank / LLM mirror) ---
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # Mirror DeepSeek through SiliconFlow so one key can serve generation.
    siliconflow_deepseek_model: str = "deepseek-ai/DeepSeek-V3"

    # --- Database ---
    database_url: str = "postgresql://pawpilot:pawpilot@localhost:5433/pawpilot"

    # --- RAG tuning ---
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 20
    final_top_k: int = 6
    rrf_k: int = 60

    # --- Agent guardrails ---
    max_iterations: int = 8
    tool_timeout_seconds: float = 60.0

    # --- Timeouts & retries (seconds) ---
    llm_timeout: float = 120.0
    llm_max_retries: int = 3
    embed_timeout: float = 60.0
    embed_max_retries: int = 3
    db_timeout: float = 30.0

    @field_validator("default_provider")
    @classmethod
    def _valid_default_provider(cls, value: str) -> str:
        if value not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"default_provider must be one of {sorted(SUPPORTED_PROVIDERS)}, got {value!r}"
            )
        return value

    @property
    def provider_defaults(self) -> dict[str, dict[str, str]]:
        """Resolve (base_url, api_key, model) for each provider id."""
        return {
            PROVIDER_DEEPSEEK: {
                "base_url": self.deepseek_base_url,
                "api_key": self.deepseek_api_key,
                "model": self.deepseek_model,
            },
            PROVIDER_QWEN: {
                "base_url": self.dashscope_base_url,
                "api_key": self.dashscope_api_key,
                "model": self.qwen_model,
            },
        }

    def provider_config(self, provider: str) -> dict[str, str]:
        cfg = self.provider_defaults.get(provider)
        if cfg is None:
            raise ValueError(
                f"Unknown provider: {provider!r}. Use one of {sorted(SUPPORTED_PROVIDERS)}."
            )
        if not cfg["api_key"]:
            raise ValueError(
                f"API key for provider {provider!r} is not set "
                f"(check .env / environment variables)."
            )
        return cfg

    def resolve_generation_provider(self) -> tuple[str, str, str]:
        """Return (base_url, api_key, model) for the active generation provider.

        Falls back to SiliconFlow-hosted DeepSeek when the native DeepSeek key
        is absent and SiliconFlow is available. This lets PawPilot run with a
        single SiliconFlow key for embedding + rerank + generation.
        """
        settings = get_settings()
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
        if settings.dashscope_api_key:
            return (
                settings.dashscope_base_url,
                settings.dashscope_api_key,
                settings.qwen_model,
            )
        raise ValueError("No generation provider key configured.")

    def validate_runtime(self) -> None:
        """Fail fast on startup if required configuration is missing.

        Called from application entrypoints so that misconfiguration surfaces
        immediately rather than mid-request.
        """
        if not self.siliconflow_api_key:
            raise ValueError(
                "SILICONFLOW_API_KEY is required for embedding/rerank. "
                "Set it in .env or environment variables."
            )
        if self.database_url is None or "postgresql://" not in self.database_url:
            raise ValueError("DATABASE_URL must be a postgresql:// URI.")
        # Validate that at least one generation provider is configured.
        # SiliconFlow also serves generation via its DeepSeek mirror.
        if not self.deepseek_api_key and not self.dashscope_api_key and not self.siliconflow_api_key:
            raise ValueError(
                "At least one generation provider key must be set: "
                "DEEPSEEK_API_KEY, DASHSCOPE_API_KEY or SILICONFLOW_API_KEY."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
