"""Centralised configuration, read from environment variables / .env.

Transversal like ``models/``: any layer may read it, but only ``integrations/``
is allowed to use the credential fields (rule R-05).
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
    # defaults (rule R-05): the real URLs come from .env.
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

    # =====================================================================
    # Reto 01 -- voice app (api/app_voice.py). docs/11 section 2.
    # =====================================================================
    openai_api_key: str = ""
    # datos.gov.co application token (optional). Validated at startup: a 403
    # drops it and the client continues anonymously (docs/09 section 2).
    datos_gov_app_token: str = ""
    # HMAC key for the anonymous session token (R-28). 32 random bytes.
    session_signing_key: str = ""
    session_token_ttl_hours: int = 2
    # Comma-separated origins allowed by CORS (the web project).
    allowed_origins: str = "http://localhost:4321"
    # In-memory rate limit per session token and per IP (R-28).
    rate_limit_per_minute: int = 120

    # -- Dataset (docs/09) --------------------------------------------------
    dataset_base_url: str = "https://www.datos.gov.co"
    dataset_id: str = "s2ru-bqt6"
    # G3 measured 0.8-2.7 s for a cold TLS connect from Colombia: 2 s failed.
    dataset_connect_timeout_s: float = 4.0
    dataset_read_timeout_s: float = 4.0
    dataset_cache_fresh_s: int = 60
    dataset_cache_stale_s: int = 24 * 3600
    tool_deadline_s: float = 6.0  # common foreground deadline (R-25)
    lexicon_path: Path = REPO_ROOT / "data" / "lexicon.json"
    reto01_domain_path: Path = REPO_ROOT / "config" / "domains" / "reto01_ips.yaml"
    style_policy_path: Path = REPO_ROOT / "config" / "style_policy.yaml"

    # -- Voice engines (D-11, verified in G2) --------------------------------
    openai_realtime_model: str = "gpt-realtime-2.1"
    openai_realtime_voice: str = "marin"
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"
    gemini_live_model: str = "gemini-3.8-live"
    gemini_live_voice: str = "Kore"
    realtime_credential_ttl_s: int = 600

    # -- Cloned voice (D-20). Optional: without the key /health only offers
    # the engine voice and /speech/session answers 503 SYNTH_UNAVAILABLE.
    cartesia_api_key: str = ""
    cartesia_voice_id: str = ""
    cartesia_model: str = "sonic-3.6"
    cartesia_version: str = "2026-08-14"
    cartesia_voice_label: str = "Voz clonada del equipo"
    speech_token_ttl_s: int = 600

    # -- Analyst profiles (D-10, verified in G3) -----------------------------
    # fast: text 1.1 s p50, audio 1.4-2.2 s p50, schema 3/3. deep: text 1.3 s.
    # OpenAI audio models reject json_schema, so the acoustic branch is Gemini only.
    analyst_fast_model: str = "gemini-3.5-flash-lite"
    analyst_deep_model: str = "gpt-5.4-mini"
    analyst_deadline_s: float = 3.0

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def database_url_safe(self) -> str:
        """The connection URL with the password masked, safe to print or log."""
        return mask_password(self.database_url)


def mask_password(url: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
