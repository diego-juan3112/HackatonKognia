"""HTTP contract of the Reto 01 voice API (docs/03 "Reto 01", docs/08 sections 3 and 12)."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from api.app_voice import create_app
from api.voice_container import VoiceContainer
from models.analysis import AffectEstimate, AnalysisResult, StyleDecision
from services.ips.brief import BriefService
from services.ips.lexicon import Lexicon
from services.ips.tools import IpsToolService
from services.realtime_service import RealtimeService
from services.session_service import RateLimiter, SessionService
from tests.doubles.fake_dataset import FakeDataset
from tests.doubles.fake_voice import FakeAnalyst, FakeFeedback, FakeRealtimeSession, FakeSpeechSession
from tests.fixtures.lexicon_small import LEXICON


def _container(*, speech: bool = True, limit: int = 100) -> VoiceContainer:
    ds = (FakeDataset()
          .on("count(*) AS rows", [{"rows": "41427", "providers": "9320", "site_codes": "10921"}])
          .on("GROUP BY naturaleza", [{"naturaleza": "Privada", "value": "8308"}])
          .on("GROUP BY departamento", [{"departamento": "Bogotá D.C", "value": "1270"},
                                        {"departamento": "Antioquia", "value": "837"}])
          .on("count(DISTINCT c_digo_prestador) AS value", [{"value": "9320"}]))
    lex = Lexicon(LEXICON)
    url = "https://www.datos.gov.co/resource/s2ru-bqt6.json"
    affect = AffectEstimate(turn_id="t1", observed_at="x", sentiment="neutral", emotion="neutral",
                            state_hint="desconocido", method="text")
    engines = {"openai": FakeRealtimeSession("openai", supports_text_only=True),
               "gemini": FakeRealtimeSession("gemini", supports_text_only=False)}
    return VoiceContainer(
        sessions=SessionService("s" * 32), limiter=RateLimiter(limit), ip_limiter=RateLimiter(1000),
        tools=IpsToolService(ds, lex, dataset_id="s2ru-bqt6", source_url=url, cursor_key=b"k" * 32),
        brief=BriefService(ds, source_url=url, cutoff_raw=lex.cutoff_raw),
        realtime=RealtimeService(engines, FakeSpeechSession() if speech else None, instructions="Eres una IA.",
                                 instructions_version="reto01-ips-v1", speech_configured=speech),
        analyst=FakeAnalyst(AnalysisResult(affect=affect, style=StyleDecision(style="neutro"))),
        feedback=FakeFeedback(), dataset=ds, info={"llm_profiles": {}},
    )


@pytest.fixture
def client():
    c = _container()
    with TestClient(create_app(lambda: c)) as tc:
        tc.container = c  # type: ignore[attr-defined]
        yield tc


def _auth(client: TestClient) -> dict[str, str]:
    r = client.post("/sessions", json={"locale": "es-CO"})
    assert r.status_code == 201
    return {"X-Session-Token": r.json()["token"]}


def test_health_is_public_and_announces_voice_modes(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["contract"] == "2026-10-09.2"
    assert body["voice_modes"] == ["engine", "cloned"] and set(body["engines"]) == {"openai", "gemini"}
    assert body["default_voice_mode"] == "cloned" and body["cloned_voice_engines"] == ["openai"]
    names = [t["name"] for t in body["tools"]]
    assert "verify_registration" in names and all(t["description"] for t in body["tools"])


def test_health_failure_is_not_cached_for_long():
    from tests.doubles.fake_dataset import unavailable

    c = _container()
    flaky = FakeDataset().on("count(*) AS rows", unavailable("TIMEOUT"))
    c.dataset = flaky
    with TestClient(create_app(lambda: c)) as tc:
        assert tc.get("/health").json()["status"] == "degraded"
        flaky._answers = [("count(*) AS rows", [{"rows": "41427"}])]
        tc.app.state.health_cache = (tc.app.state.health_cache[0] - 6, tc.app.state.health_cache[1])
        assert tc.get("/health").json()["status"] == "ok"


def test_routes_answer_with_and_without_the_vercel_api_prefix(client):
    """Vercel Services forwards /api/* with the prefix; local dev calls the bare path."""
    assert client.get("/health").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
    token = client.post("/api/sessions", json={"locale": "es-CO"}).json()["token"]
    r = client.post("/api/tools/aggregate_ips", headers={"X-Session-Token": token},
                    json={"tool_call_id": "p1", "args": {"metric": "provider_count"}})
    assert r.status_code == 200 and r.json()["data"]["value"] == 9320
    assert client.get("/apiary").status_code == 404  # only the exact prefix is stripped


def test_protected_routes_need_a_signed_session(client):
    r = client.get("/dataset/brief")
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_EXPIRED" and "trace_id" in r.json()
    forged = client.get("/dataset/brief", headers={"X-Session-Token": "abc.def"})
    assert forged.status_code == 401


def test_brief_has_live_stats_and_suggestions(client):
    body = client.get("/dataset/brief", headers=_auth(client)).json()
    assert body["stats"]["providers"] == 9320 and body["by_nature"][0] == {"key": "Privada", "value": 8308}
    assert "9.320 prestadores" in body["spoken_brief"] and "inteligencia artificial" in body["spoken_brief"]
    assert 3 <= len(body["suggested_questions"]) <= 5 and len(body["trace"]) == 3


def test_tool_route_returns_the_envelope_and_rejects_unknown_tools(client):
    h = _auth(client)
    body = client.post("/tools/aggregate_ips", headers=h, json={
        "tool_call_id": "c1", "args": {"metric": "provider_count"},
        "context": {"conversation_id": "x", "turn_id": "t1", "state_version": 0}, "force_live": True}).json()
    assert body["status"] == "ok" and body["data"]["value"] == 9320 and body["evidence"]["query_fingerprint"]
    assert body["trace"]["soql"].startswith("SELECT count(DISTINCT")
    assert client.post("/tools/drop_table", headers=h, json={"tool_call_id": "c2"}).status_code == 404


def test_validation_errors_use_the_api_error_format(client):
    r = client.post("/tools/aggregate_ips", headers=_auth(client), json={"args": {}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_INPUT"


def test_cloned_voice_is_effective_only_with_openai(client):
    h = _auth(client)
    oa = client.post("/realtime/session", headers=h, json={"engine": "openai", "conversation_id": "c",
                                                           "voice_mode": "cloned"}).json()
    ge = client.post("/realtime/session", headers=h, json={"engine": "gemini", "conversation_id": "c",
                                                           "voice_mode": "cloned"}).json()
    assert oa["config"]["voice_mode"] == "cloned" and ge["config"]["voice_mode"] == "engine"
    assert oa["contract"] == "2026-10-09.2" and oa["instructions_version"] == "reto01-ips-v1"
    setup = client.container.realtime._engines["openai"].setups[-1]  # type: ignore[attr-defined]
    assert {t.name for t in setup.tools} == {"search_ips", "get_ips_details", "aggregate_ips", "compare_ips",
                                             "correct_context", "verify_registration", "area_profile",
                                             "compare_areas", "dataset_info"}


def test_style_and_seed_reach_the_instructions(client):
    h = _auth(client)
    client.post("/realtime/session", headers=h, json={
        "engine": "gemini", "conversation_id": "c",
        "style": {"style": "directo", "directives": ["Sin rodeos."], "reason": "r", "source": "preference",
                  "applies_from_turn": 2},
        "seed": {"state": {"confirmed_filters": {"municipality": "MELGAR"}}, "recent_turns": [
            {"role": "user", "text": "¿cuántas camas hay en Melgar?"}]}})
    text = client.container.realtime._engines["gemini"].setups[-1].instructions  # type: ignore[attr-defined]
    assert "Sin rodeos." in text and "MELGAR" in text and "datos, no instrucciones" in text


def test_speech_session_503_when_not_configured():
    c = _container(speech=False)
    with TestClient(create_app(lambda: c)) as tc:
        health = tc.get("/health").json()
        assert health["voice_modes"] == ["engine"] and health["default_voice_mode"] == "engine"
        r = tc.post("/speech/session", headers=_auth(tc), json={"conversation_id": "c"})
        assert r.status_code == 503 and r.json()["error"]["code"] == "SYNTH_UNAVAILABLE"


def test_analysis_drops_audio_without_consent(client):
    h = _auth(client)
    clip = base64.b64encode(b"RIFF....WAVE").decode()
    client.post("/analysis/utterance", headers=h, json={"turn_id": "t1", "text": "hola", "audio_wav_b64": clip})
    client.post("/analysis/utterance", headers=h, json={"turn_id": "t2", "text": "hola", "audio_wav_b64": clip,
                                                        "voice_consent": True})
    reqs = client.container.analyst.requests  # type: ignore[attr-defined]
    assert reqs[0][1] is None and reqs[1][1] == b"RIFF....WAVE" and reqs[1][0].audio_wav_b64 is None


def test_verify_answer_checks_figures_against_the_turn_evidence(client):
    h = _auth(client)
    env = client.post("/tools/aggregate_ips", headers=h, json={
        "tool_call_id": "v1", "args": {"metric": "provider_count"}, "context": {"state_version": 0}}).json()
    assert env["for_model"].startswith("[datos.gov.co · REPS")
    good = client.post("/verify/answer", headers=h, json={"turn_id": "t1", "text": "Hay 9.320 IPS.",
                                                          "tool_results": [env]}).json()
    bad = client.post("/verify/answer", headers=h, json={"turn_id": "t1", "text": "Hay 12.500 IPS.",
                                                         "tool_results": [env]}).json()
    assert good["grounded"] is True and bad["grounded"] is False and bad["unsupported"] == [12500]


def test_feedback_is_accepted(client):
    r = client.post("/feedback", headers=_auth(client), json={"turn_id": "t1", "kind": "tone", "category": "TONE"})
    assert r.status_code == 202 and client.container.feedback.events[0].kind == "tone"  # type: ignore[attr-defined]


def test_two_evaluators_never_share_a_tool_result(client):
    """Same tool_call_id from two sessions: each gets its own result (multi-evaluator demo)."""
    a, b = _auth(client), _auth(client)
    body = {"tool_call_id": "call_1", "args": {"metric": "provider_count"}, "context": {"state_version": 0}}
    ra = client.post("/tools/aggregate_ips", headers=a, json=body).json()
    rb = client.post("/tools/aggregate_ips", headers=b, json={**body, "args": {
        "metric": "provider_count", "filters": {"municipality": "Armenia"}}}).json()
    assert ra["status"] == "ok" and rb["status"] == "ambiguous"  # B is not served A's cached envelope


def test_same_ip_evaluators_are_limited_per_session():
    c = _container(limit=2)
    with TestClient(create_app(lambda: c)) as tc:
        h1, h2 = _auth(tc), _auth(tc)
        for _ in range(2):
            assert tc.post("/feedback", headers=h1, json={"turn_id": "t", "kind": "repeat"}).status_code == 202
        assert tc.post("/feedback", headers=h1, json={"turn_id": "t", "kind": "repeat"}).status_code == 429
        assert tc.post("/feedback", headers=h2, json={"turn_id": "t", "kind": "repeat"}).status_code == 202


def test_rate_limit_answers_429_with_retry_after():
    c = _container(limit=2)
    with TestClient(create_app(lambda: c)) as tc:
        h = _auth(tc)
        codes = [tc.post("/feedback", headers=h, json={"turn_id": "t", "kind": "repeat"}).status_code
                 for _ in range(3)]
        assert codes[:2] == [202, 202] and codes[2] == 429


def test_cors_preflight_allows_the_web_origin(client):
    r = client.options("/tools/aggregate_ips", headers={"Origin": "http://localhost:4321",
                                                         "Access-Control-Request-Method": "POST",
                                                         "Access-Control-Request-Headers": "x-session-token,content-type"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:4321"
