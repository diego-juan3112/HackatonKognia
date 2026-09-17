"""A deterministic chat model for offline development, tests and demos.

It is not a mock that returns one canned string: it reads the prompt the node
sent and answers in the shape that node expects. That makes the whole graph
exercisable -- classification, extraction and answering -- with no network, no
credentials and no cost, which is what AGENTS.md section 11 requires.

The heuristics are deliberately crude. This model exists to prove the pipeline
is wired correctly, never to be good at the task.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_CATALOGUE_LINE = re.compile(r"^-\s*([\w.-]+)\s*:\s*(.+)$", re.MULTILINE)
_STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "y", "o", "que", "en", "a",
    "por", "para", "con", "es", "cual", "cuales", "como", "the", "of", "to",
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


class FakeChatModel(BaseChatModel):
    """Answers according to what the calling node asked for."""

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        return self

    # -- prompt shape detection -------------------------------------------
    @staticmethod
    def _system_text(messages: list[BaseMessage]) -> str:
        return "\n".join(
            str(m.content) for m in messages if isinstance(m, SystemMessage)
        )

    @staticmethod
    def _user_text(messages: list[BaseMessage]) -> str:
        return "\n".join(
            str(m.content) for m in messages if not isinstance(m, SystemMessage)
        )

    def _answer(self, messages: list[BaseMessage]) -> str:
        system = self._system_text(messages)
        user = self._user_text(messages)

        # 1. Classification prompt: pick the catalogue entry with the most
        #    word overlap, else the declared fallback.
        if "classify" in system.lower():
            entries = _CATALOGUE_LINE.findall(system)
            fallback = "unknown"
            match = re.search(r"reply exactly:\s*\n?\s*(\S+)", system, re.IGNORECASE)
            if match:
                fallback = match.group(1).strip()

            user_words = _words(user)
            best, best_score = fallback, 0
            for name, description in entries:
                score = len(user_words & _words(f"{name} {description}"))
                if score > best_score:
                    best, best_score = name, score
            return best

        # 2. Extraction prompt: return valid-but-empty JSON, so the graph
        #    takes the "field still missing" path and asks the user.
        if "json object" in system.lower():
            return "{}"

        # 3. Answer prompt: quote the retrieved context verbatim. If the
        #    answer echoes the corpus, retrieval really did feed respond.
        block = re.search(r"Context:\s*(.+)", system, re.DOTALL)
        if block:
            context = block.group(1).strip()
            if context and not context.startswith("(sin contexto"):
                first = context.split("\n\n")[0].strip()
                return f"[fake-llm] {first}"
        return "[fake-llm] No tengo contexto indexado para responder eso."

    # -- BaseChatModel ----------------------------------------------------
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(content=self._answer(messages))
        return ChatResult(generations=[ChatGeneration(message=message)])
