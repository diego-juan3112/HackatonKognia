"""
Adaptador de infraestructura: construye el LLM concreto según config.

Este es el ÚNICO archivo que sabe si estamos hablando con Azure OpenAI
o con OpenAI directo. El resto del agente (application/agent_graph.py)
solo conoce el puerto `LLMPort` (ver domain/ports.py).
"""

from langchain_openai import AzureChatOpenAI, ChatOpenAI

from agent_core.config import Settings
from agent_core.domain.ports import LLMPort


def build_llm(settings: Settings) -> LLMPort:
    """Devuelve el chat model configurado (Azure u OpenAI)."""

    if settings.model_provider == "azure":
        if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
            raise RuntimeError(
                "MODEL_PROVIDER=azure pero faltan AZURE_OPENAI_ENDPOINT "
                "y/o AZURE_OPENAI_API_KEY en tu .env"
            )
        return AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_deployment=settings.azure_openai_deployment,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            temperature=0,
        )

    if settings.model_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError(
                "MODEL_PROVIDER=openai pero falta OPENAI_API_KEY en tu .env"
            )
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )

    raise ValueError(f"MODEL_PROVIDER desconocido: {settings.model_provider!r}")
