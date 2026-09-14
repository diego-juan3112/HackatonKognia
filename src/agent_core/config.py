"""
Configuración centralizada del agente.

Toda la app lee configuración de aquí (y esto lee de variables de
entorno / .env). Así, cambiar de OpenAI -> Azure OpenAI el día del
hackathon es cuestión de variables de entorno, no de tocar código.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Selector de proveedor de modelo
    model_provider: Literal["azure", "openai"] = "openai"

    # Azure OpenAI / Azure AI Foundry
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # OpenAI directo
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Herramientas
    tavily_api_key: str = ""

    # App
    app_env: str = "local"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
