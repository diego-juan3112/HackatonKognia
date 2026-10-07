"""The agent knows who it is talking to -- and never sends the full cedula.

Uses a model that records the exact prompt it receives, so the assertions are
about what would really reach Gemini.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver

from models.auth import User
from services.chat_service import ChatService
from services.graph.builder import build_graph

CEDULA = "1053812345"


class RecordingModel(BaseChatModel):
    """Answers every prompt with a fixed reply and keeps what it was sent."""

    prompts: list = []

    @property
    def _llm_type(self) -> str:
        return "recording"

    def _generate(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any
    ) -> ChatResult:
        self.prompts.append(messages)
        reply = "horario" if "classify" in str(messages[0].content).lower() else "ok"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])


def _answer_prompt(model: RecordingModel) -> str:
    """The system instruction of the prompt that produced the reply."""
    answer_prompts = [p for p in model.prompts if "Context:" in str(p[0].content)]
    assert answer_prompts, "the answer branch never called the model"
    return str(answer_prompts[-1][0].content)


async def _send(retriever, domain, conversations) -> RecordingModel:
    model = RecordingModel(prompts=[])
    graph = build_graph(llm=model, retriever=retriever, domain=domain, checkpointer=MemorySaver())
    chat = ChatService(graph=graph, conversations=conversations, domain=domain)
    user = User(id=uuid4(), cedula=CEDULA, display_name="Ana", created_at=datetime.now(timezone.utc))
    await chat.send(user, "cual es el horario de atencion")
    return model


async def test_the_model_is_told_the_users_name(retriever, domain, conversations):
    model = await _send(retriever, domain, conversations)
    assert "Ana" in _answer_prompt(model)


async def test_only_the_last_four_digits_reach_the_model(retriever, domain, conversations):
    model = await _send(retriever, domain, conversations)
    prompt = _answer_prompt(model)

    assert CEDULA[-4:] in prompt
    assert CEDULA not in prompt, "the full cedula must never be sent to the LLM"


async def test_no_prompt_at_all_contains_the_full_cedula(retriever, domain, conversations):
    """Not just the answer: classification and extraction prompts too."""
    model = await _send(retriever, domain, conversations)
    for prompt in model.prompts:
        assert all(CEDULA not in str(m.content) for m in prompt)
