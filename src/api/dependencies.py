"""Composition root.

The old ``api/main.py`` built the agent at import time, which meant importing
the app required real credentials and broke tests and CI. Everything is built
here instead, once, during the app lifespan.

This is also the only file in ``api/`` allowed to name ``integrations``: it
wires the object graph. Request handlers depend on the assembled container, so
the layer rule of AGENTS.md section 2 still holds at call time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import Settings, get_settings
from integrations.llm.factory import build_llm
from integrations.retrieval.chroma_retriever import ChromaRetriever
from integrations.retrieval.embeddings import build_embedder
from models.domain_config import DomainSpec
from models.ports import LLMPort, RetrievalPort
from services.domain_loader import load_domain
from services.graph.builder import build_graph


@dataclass(slots=True)
class Container:
    """Everything the request handlers need, assembled once."""

    settings: Settings
    domain: DomainSpec
    llm: LLMPort
    retriever: RetrievalPort
    graph: Any


def build_container(settings: Settings | None = None) -> Container:
    """Assemble the application. Called from the lifespan and from tests."""
    settings = settings or get_settings()

    domain = load_domain(settings.domain_config_path)
    llm = build_llm(settings)
    retriever = ChromaRetriever(
        path=settings.chroma_path,
        collection_name=settings.chroma_collection,
        embedder=build_embedder(
            settings.embedding_provider,
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
        ),
    )
    graph = build_graph(
        llm=llm,
        retriever=retriever,
        domain=domain,
        top_k=settings.retrieval_top_k,
    )
    return Container(
        settings=settings,
        domain=domain,
        llm=llm,
        retriever=retriever,
        graph=graph,
    )
