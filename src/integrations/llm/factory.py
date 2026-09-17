"""Infrastructure adapter: build the concrete chat model from settings.

This is the only file that knows whether we are talking to Azure OpenAI, to
OpenAI directly, or to nothing at all. Everything above it sees only LLMPort.
"""

from __future__ import annotations

from config import Settings
from integrations.llm.fake_llm import FakeChatModel
from models.ports import LLMPort


def build_llm(settings: Settings) -> LLMPort:
    """Return the chat model selected by ``MODEL_PROVIDER``."""

    if settings.model_provider == "fake":
        return FakeChatModel()

    if settings.model_provider == "azure":
        from langchain_openai import AzureChatOpenAI

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
        from langchain_openai import ChatOpenAI

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
