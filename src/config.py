"""Centralised configuration, read from environment variables / .env.

Transversal like ``models/``: any layer may read it, but only ``integrations/``
is allowed to use the credential fields (AGENTS.md section 8).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Model provider selector.
    # "fake" runs the whole graph deterministically with no network and no
    # credentials -- it is what tests and the offline demo use.
    model_provider: Literal["azure", "openai", "fake"] = "fake"

    # Azure OpenAI / Azure AI Foundry
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # OpenAI direct
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Optional tools
    tavily_api_key: str = ""

    # Domain configuration: which YAML describes the business domain.
    domain_config_path: Path = REPO_ROOT / "config" / "domains" / "faq_demo.yaml"

    # Knowledge base
    chroma_path: Path = REPO_ROOT / ".chroma"
    chroma_collection: str = "kognia"
    embedding_provider: Literal["openai", "fake"] = "fake"
    embedding_model: str = "text-embedding-3-small"
    retrieval_top_k: int = 4

    # App
    app_env: str = "local"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
