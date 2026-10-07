"""Infrastructure adapter: build the chat model from settings.

This is the only file that knows the LLM is Gemini. Everything above it sees
only ``LLMPort``, which is why swapping providers never touched a graph node.

Test doubles live in tests/doubles/, not here: the product always talks to the
real model.
"""

from __future__ import annotations

from typing import Any

from config import Settings
from models.ports import LLMPort


def build_llm(settings: Settings) -> LLMPort:
    """Return the Gemini chat model configured in settings."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not settings.gemini_api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY en tu .env. "
            "Se obtiene en https://aistudio.google.com/apikey"
        )

    kwargs: dict[str, Any] = {
        "model": settings.gemini_model,
        "google_api_key": settings.gemini_api_key,
        "temperature": 0,
        "timeout": settings.gemini_timeout_seconds,
        "max_retries": settings.gemini_max_retries,
    }
    # Only send the thinking control that applies. `thinking_level` is the
    # Gemini 3+ knob (an alias of the library's `reasoning_effort` field);
    # `thinking_budget` is the 2.5 one.
    if settings.gemini_thinking_level:
        kwargs["thinking_level"] = settings.gemini_thinking_level
    if settings.gemini_thinking_budget is not None:
        kwargs["thinking_budget"] = settings.gemini_thinking_budget

    return ChatGoogleGenerativeAI(**kwargs)
