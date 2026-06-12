from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment / .env.

    When no Anthropic key is configured the engine falls back to a
    deterministic mock LLM so the full pipeline (and the test suite)
    runs without external dependencies.
    """

    model_config = SettingsConfigDict(env_prefix="AGENTFLOW_", env_file=".env", extra="ignore")

    anthropic_api_key: str | None = None
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 1024

    # Below this classification confidence a workflow is routed to a human
    # reviewer instead of straight-through processing.
    review_confidence_threshold: float = 0.80

    mock_mode: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
