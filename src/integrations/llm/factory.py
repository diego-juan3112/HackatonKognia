"""Infrastructure adapter: build the concrete chat model from settings.

This is the only file that knows which vendor is answering. Everything above it
sees only ``LLMPort``.

Imports are inside each branch on purpose: selecting "fake" must not require
the NVIDIA or OpenAI packages to be importable, which is what keeps the test
suite runnable with a minimal environment.
"""

from __future__ import annotations

from config import Settings
from integrations.llm.fake_llm import FakeChatModel
from models.ports import LLMPort


def build_llm(settings: Settings) -> LLMPort:
    """Return the chat model selected by ``MODEL_PROVIDER``."""

    if settings.model_provider == "fake":
        return FakeChatModel()

    if settings.model_provider == "nvidia":
        # ChatOpenAI, not ChatNVIDIA, and that is deliberate.
        #
        # NVIDIA NIM speaks the OpenAI protocol, so pointing ChatOpenAI at its
        # base_url works. We need that because `reasoning_effort` has to reach
        # the API: langchain-nvidia-ai-endpoints silently drops it (verified by
        # token count -- 100 output tokens with it, same as without), and that
        # parameter is the difference between ~19s and ~3s per call.
        #
        # It also removes a dependency that was pinned to an old line because
        # its current release demands langchain-core 1.x.
        #
        # No OpenAI account is involved: the key is the NVIDIA one and the
        # traffic goes to integrate.api.nvidia.com.
        from langchain_openai import ChatOpenAI

        if not settings.nvidia_api_key:
            raise RuntimeError(
                "MODEL_PROVIDER=nvidia pero falta NVIDIA_API_KEY en tu .env. "
                "Consiguela gratis en https://build.nvidia.com"
            )
        return ChatOpenAI(
            model=settings.nvidia_model,
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            temperature=0,
            extra_body={"reasoning_effort": settings.nvidia_reasoning_effort},
        )

    # --- Respaldo de pago -------------------------------------------------
    # Se conservan por si el tier gratuito de NVIDIA se agota a mitad de la
    # demo: cambiar de proveedor es una variable de entorno. Ver AGENTS.md 1.3.

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
