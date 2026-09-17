"""API layer: the contract, and the regression that importing must be cheap."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.dependencies import build_container
from api.main import app
from models.retrieval import Document


@pytest.fixture
def client(settings, monkeypatch):
    """Build the app with offline settings instead of the real environment."""
    container = build_container(settings)
    container.retriever.index(
        [
            Document(
                source="horarios.md",
                text="La atencion presencial es de lunes a viernes de 8:00 a 17:00.",
            )
        ]
    )
    monkeypatch.setattr("api.main.build_container", lambda: container)
    with TestClient(app) as test_client:
        yield test_client


def test_importing_the_app_needs_no_credentials():
    """Regression: the old main.py built the agent at import time.

    If this module imported successfully, the import is already side-effect
    free -- but assert on the app object so the intent is explicit.
    """
    assert app.title.startswith("Kognia")


def test_health_reports_what_is_wired(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["model_provider"] == "fake"
    assert body["domain"] == "faq_demo"
    assert body["indexed_chunks"] >= 1


def test_chat_answers_and_reports_its_sources(client):
    body = client.post(
        "/chat", json={"message": "cual es el horario de atencion", "thread_id": "t1"}
    ).json()

    assert body["route"] == "answer"
    assert body["sources"] == ["horarios.md"]
    assert body["reply"]


def test_chat_surfaces_missing_fields(client):
    body = client.post(
        "/chat", json={"message": "como va mi solicitud radicada", "thread_id": "t2"}
    ).json()

    assert body["route"] == "collect"
    assert body["missing_fields"] == ["numero_radicado"]


def test_empty_message_is_rejected(client):
    assert client.post("/chat", json={"message": "", "thread_id": "t3"}).status_code == 422
