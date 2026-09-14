"""
Capa de entrada (API): expone el agente vía FastAPI.

Esta es la única capa que sabe que existe HTTP. No tiene lógica de
negocio: arma dependencias (config, llm, tools, agente) y las expone.
"""

from langchain_core.messages import HumanMessage
from fastapi import FastAPI
from pydantic import BaseModel

from agent_core.application.agent_graph import build_agent
from agent_core.config import get_settings
from agent_core.infrastructure.llm_factory import build_llm
from agent_core.infrastructure.tools import default_toolset

app = FastAPI(title="Agente General - Kognia Challenge", version="0.1.0")

settings = get_settings()
llm = build_llm(settings)
tools = default_toolset(settings)
agent = build_agent(llm, tools)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


class ChatResponse(BaseModel):
    reply: str
    thread_id: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_provider": settings.model_provider}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    config = {"configurable": {"thread_id": payload.thread_id}}
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=payload.message)]},
        config=config,
    )
    last_message = result["messages"][-1]
    return ChatResponse(reply=last_message.content, thread_id=payload.thread_id)


# Para correr localmente:
#   uvicorn api.main:app --reload --app-dir src --port 8000
