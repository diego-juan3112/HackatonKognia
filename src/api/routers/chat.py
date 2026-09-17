"""Chat endpoints. HTTP in, HTTP out -- no business logic.

The handler translates a request into graph state, runs the graph and maps the
result back. Every decision it reports (intent, route, missing fields) was made
by ``services/``; this layer only reads it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.dependencies import Container
from models.conversation import RouteDecision, TurnResult
from services.graph.state import initial_state

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str = "default"


def get_container(request: Request) -> Container:
    return request.app.state.container


@router.post("/chat", response_model=TurnResult)
async def chat(
    payload: ChatRequest,
    container: Container = Depends(get_container),
) -> TurnResult:
    config = {"configurable": {"thread_id": payload.thread_id}}
    result = await container.graph.ainvoke(initial_state(payload.message), config=config)

    reply = ""
    if result.get("messages"):
        reply = str(result["messages"][-1].content)

    return TurnResult(
        reply=reply,
        thread_id=payload.thread_id,
        intent=result.get("intent"),
        route=result.get("route") or RouteDecision.ANSWER,
        missing_fields=result.get("missing_fields", []),
        sources=sorted({item.source for item in result.get("retrieved", [])}),
    )
