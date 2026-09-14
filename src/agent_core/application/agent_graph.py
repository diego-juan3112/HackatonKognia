"""
Capa de aplicación: arma el agente (el "grafo") usando LangGraph.

Usamos `create_react_agent` de langgraph.prebuilt, que ya implementa
el ciclo ReAct (Reasoning + Acting):

    usuario -> [nodo LLM decide] -> ¿necesita una tool?
                    |                       |
                    | no                    | sí
                    v                       v
                respuesta          [nodo ejecuta tool] -> vuelve al LLM

Esto es exactamente lo mismo que tendrías escribiendo tu propio
StateGraph con nodos "agent" y "tools" y un edge condicional entre
ellos (así es por dentro), pero ya viene resuelto y probado. Para el
hackathon, empieza aquí; si necesitas un flujo más custom (varios
agentes especializados, pasos fijos antes/después del LLM, etc.),
mira `langgraph-supervisor` / `langgraph-swarm` o construye tu propio
StateGraph a mano (queda documentado en la guía .md).
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from agent_core.domain.ports import LLMPort, ToolPort

SYSTEM_PROMPT = (
    "Eres un agente asistente general. Piensa paso a paso, usa las "
    "herramientas disponibles cuando aporten datos que no sabes de "
    "memoria, y responde siempre en español de forma clara y directa."
)


def build_agent(llm: LLMPort, tools: list[ToolPort]):
    """
    Compila y devuelve el agente (grafo ya compilado, listo para
    `.invoke(...)` / `.ainvoke(...)` / `.stream(...)`).

    El `checkpointer` (MemorySaver) le da memoria de conversación por
    `thread_id`: útil para que el agente recuerde el contexto durante
    la demo. En memoria basta para el hackathon; en producción se
    cambiaría por un checkpointer persistente (ej. Postgres).
    """
    checkpointer = MemorySaver()

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
