"""
Test de humo: valida que el grafo de LangGraph compila y responde,
SIN llamar a Azure ni a OpenAI (usa un chat model falso). Ideal para
correr en cualquier momento del hackathon y confirmar que la
integración LangGraph no se rompió, aunque no tengas internet o
créditos a mano.

Ejecutar con:  pytest -q
"""

from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent_core.application.agent_graph import build_agent
from agent_core.infrastructure.tools.calculator_tool import calculator


class _FakeToolCallingChatModel(BaseChatModel):
    """
    Chat model falso mínimo que sí implementa `bind_tools` (a diferencia
    de los Fake*ChatModel que trae langchain_core por defecto), para
    poder ejercitar `create_react_agent` de punta a punta sin llamar a
    ninguna API real.
    """

    response_text: str = "Hola, soy el agente base del equipo."

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling-chat-model"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):
        # El agente ReAct solo necesita que el modelo acepte el bind;
        # como esta respuesta falsa nunca pide una tool, no hace falta
        # registrar los tools de verdad.
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(content=self.response_text)
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_agent_responds_without_real_llm():
    fake_llm = _FakeToolCallingChatModel()

    agent = build_agent(fake_llm, tools=[calculator])

    result = agent.invoke(
        {"messages": [("user", "hola")]},
        config={"configurable": {"thread_id": "test-thread"}},
    )

    assert result["messages"][-1].content == "Hola, soy el agente base del equipo."


def test_calculator_tool_directly():
    assert calculator.invoke({"expression": "2 + 2 * 10"}) == "22"
