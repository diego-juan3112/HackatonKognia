"""Centralised configuration, read from environment variables / .env.

Transversal like ``models/``: any layer may read it, but only ``integrations/``
is allowed to use the credential fields (AGENTS.md section 8).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed by migrations/001_init.sql -> document_chunks.embedding vector(768).
# Changing the embedding model to one with a different width means writing a
# new migration and reindexing; pgvector will not convert the column for you.
EMBEDDING_DIMENSIONS = 768


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # -- Model provider ---------------------------------------------------
    # "fake"   runs the whole graph deterministically, no network, no key.
    # "nvidia" is the real default (free tier at build.nvidia.com).
    # "openai"/"azure" are kept as a paid fallback if NVIDIA credits run out
    # mid-demo -- switching is one environment variable.
    model_provider: Literal["nvidia", "azure", "openai", "fake"] = "fake"

    # NVIDIA NIM
    #
    # gpt-oss-20b chosen by measurement, not by reputation (2026-09-23):
    #   nemotron-3-super-120b-a12b  1.1s median but 3 of 6 calls -> HTTP 503
    #   gpt-oss-20b                 7.3s median, 0 of 6 failed, all three
    #                               prompt shapes correct (intent, JSON, Spanish)
    #
    # Despite the name it is an open-weights model served by NVIDIA: no OpenAI
    # account and no payment involved.
    #
    # Do NOT trust ChatNVIDIA.get_available_models() when picking another one --
    # its catalogue is stale and lists models that return 410 Gone. Ask the API
    # itself: GET https://integrate.api.nvidia.com/v1/models
    nvidia_api_key: str = ""
    nvidia_model: str = "openai/gpt-oss-20b"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # gpt-oss is a reasoning model and by default burns most of its budget on
    # internal thinking. Measured over 5 calls each, same prompt:
    #   sin el parametro -> mediana 19.4s, 100 tokens de salida
    #   effort="low"     -> mediana  3.3s,  27 tokens de salida
    # Same answer quality for tasks this simple. Set to "medium"/"high" only if
    # the real domain turns out to need actual reasoning.
    nvidia_reasoning_effort: str = "low"

    # Azure OpenAI / Azure AI Foundry (fallback)
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # OpenAI direct (fallback)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Optional tools
    tavily_api_key: str = ""

    # -- Database ---------------------------------------------------------
    # Points at the docker-compose container on 5433, NOT at the native
    # PostgreSQL 17 on 5432, which stays untouched.
    database_url: str = "postgresql://kognia:kognia_local_dev@localhost:5433/kognia"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    # -- Domain -----------------------------------------------------------
    domain_config_path: Path = REPO_ROOT / "config" / "domains" / "faq_demo.yaml"

    # -- Knowledge base ---------------------------------------------------
    # "local" = intfloat/multilingual-e5-base on this machine (768 dims).
    # "fake"  = deterministic hashing vectors, for tests and offline work.
    embedding_provider: Literal["local", "fake"] = "fake"
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
        return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
