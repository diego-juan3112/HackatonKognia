"""Centralised configuration, read from environment variables / .env.

Transversal like ``models/``: any layer may read it, but only ``integrations/``
is allowed to use the credential fields (AGENTS.md section 8).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed by migrations/001_init.sql -> document_chunks.embedding vector(768).
# Changing the embedding model to one with a different width means writing a
# new migration and reindexing; pgvector will not convert the column for you.
EMBEDDING_DIMENSIONS = 768


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # -- LLM: Gemini (Google AI Studio) ------------------------------------
    gemini_api_key: str = ""
    # Chosen by measurement through our own factory (2026-09-28), with the three
    # prompt shapes the graph uses (intent, JSON extraction, Spanish answer):
    #   gemini-3.5-flash-lite  ~0.6-1.0 s median, 15/15 correct, 0 failures
    #   gemini-3.8-flash       ~8.5 s, 164 reasoning tokens, 4 of 6 rate-limited
    #   gemini-2.5-flash(-lite) 404: "no longer available to new users", even
    #                          though the model list still returns them
    # This model ignores `temperature` (fixed sampling defaults) -- it warns once.
    #
    # The model list is not proof a model works: call it before choosing it.
    gemini_model: str = "gemini-3.5-flash-lite"

    # Gemini 3+ "thinks" before answering, and that thinking dominates latency.
    # flash-lite used 0 reasoning tokens even without this, so "minimal" is a
    # guard, not the source of its speed.
    # Verified that the value reaches the API: gemini-3.8-flash answers 400
    # "Thinking level MINIMAL is not supported" -- so change this together with
    # the model. 2.5 models used a token budget instead; only one is sent.
    gemini_thinking_level: str | None = "minimal"  # minimal | low | medium | high
    gemini_thinking_budget: int | None = None
    gemini_timeout_seconds: float = 30.0
    # The client retries rate-limited calls with backoff. Its default (6) can
    # hang a demo for a long time; two retries then a clear error is better.
    gemini_max_retries: int = 2

    # -- Database ---------------------------------------------------------
    # Points at the docker-compose container on 5433, NOT at a native
    # PostgreSQL on 5432. The password is deliberately absent from these
    # defaults (AGENTS.md section 8): the real URLs come from .env.
    database_url: str = "postgresql://kognia@localhost:5433/kognia"
    # Integration tests run here, never on database_url. The name MUST end in
    # "_test": the test fixtures refuse to truncate anything else.
    test_database_url: str = "postgresql://kognia@localhost:5433/kognia_test"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    # -- Domain -----------------------------------------------------------
    domain_config_path: Path = REPO_ROOT / "config" / "domains" / "faq_demo.yaml"

    # -- Knowledge base ---------------------------------------------------
    # Runs locally on CPU, no API key. Must produce EMBEDDING_DIMENSIONS.
    embedding_model: str = "intfloat/multilingual-e5-base"
    retrieval_top_k: int = 4

    # -- Auth -------------------------------------------------------------
    session_ttl_hours: int = 12

    # -- App --------------------------------------------------------------
    app_env: str = "local"
    log_level: str = "INFO"

    @property
    def database_url_safe(self) -> str:
        """The connection URL with the password masked, safe to print or log."""
        return mask_password(self.database_url)


def mask_password(url: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
