"""Smoke test of the public Reto 01 API (docs/11 section 7). httpx only.

    python -m scripts.smoke_public --base-url https://api.example.app [--origin https://web.example.app]
                                   [--web-url https://web.example.app] [--skip-engines]

One line per check with its latency and PASS/FAIL/SKIP, then a summary table.
Exits 1 if any P0 check fails. Never prints the session token nor any minted
credential (R-05): only its presence and length.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

TIMEOUT_S = 15.0

# docs/09 section 9 (corte REPS 2022-11-05)
GOLDEN = {"providers": 9320, "site_codes": 10921, "rows": 41427, "beds": 97036}
GOLDEN_NATURE = {"Privada": 8308, "Pública": 998, "Mixta": 14}


class CheckFailed(Exception):
    pass


class Skip(Exception):
    pass


def expect(cond: bool, message: str) -> None:
    if not cond:
        raise CheckFailed(message)


@dataclass
class Result:
    name: str
    priority: str
    ms: int
    outcome: str  # PASS / FAIL / SKIP
    detail: str


class Smoke:
    def __init__(self, base_url: str, origin: str | None, web_url: str | None, skip_engines: bool) -> None:
        self.base = base_url.rstrip("/")
        self.origin = origin
        self.web_url = web_url
        self.skip_engines = skip_engines
        self.http = httpx.Client(base_url=self.base, timeout=TIMEOUT_S)
        self.results: list[Result] = []
        self.token: str | None = None
        self.health: dict[str, Any] = {}

    # -- plumbing -------------------------------------------------------------

    def run(self, name: str, fn: Callable[[], str | None], priority: str = "P0") -> None:
        t0 = time.perf_counter()
        try:
            detail = fn() or ""
            outcome = "PASS"
        except Skip as exc:
            outcome, detail = "SKIP", str(exc)
        except CheckFailed as exc:
            outcome, detail = "FAIL", str(exc)
        except Exception as exc:  # noqa: BLE001 -- one broken check must not stop the rest
            outcome, detail = "FAIL", f"{type(exc).__name__}: {exc}"
        ms = int((time.perf_counter() - t0) * 1000)
        self.results.append(Result(name, priority, ms, outcome, detail))
        print(f"[{outcome:4}] {priority} {name:<42} {ms:>6} ms  {detail}", flush=True)

    def headers(self) -> dict[str, str]:
        if not self.token:
            raise CheckFailed("sin token de sesión (falló POST /sessions)")
        return {"X-Session-Token": self.token}

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        return self.http.post(path, json=body, headers=self.headers())

    def tool(self, name: str, args: dict[str, Any], *, call_id: str | None = None, state_version: int = 0,
             force_live: bool = False) -> dict[str, Any]:
        body = {"tool_call_id": call_id or str(uuid.uuid4()), "args": args,
                "context": {"conversation_id": "smoke", "turn_id": "smoke-t1", "state_version": state_version},
                "force_live": force_live}
        r = self.post(f"/tools/{name}", body)
        expect(r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    @staticmethod
    def _error_shape(r: httpx.Response) -> bool:
        try:
            body = r.json()
        except ValueError:
            return False
        return isinstance(body.get("error"), dict) and "code" in body["error"] and "trace_id" in body

    # -- checks ---------------------------------------------------------------

    def check_health(self) -> str:
        r = self.http.get("/health")
        expect(r.status_code == 200, f"HTTP {r.status_code}")
        h = self.health = r.json()
        for key in ("contract", "voice_modes", "engines", "source"):
            expect(key in h, f"falta '{key}'")
        expect(h["source"].get("ok") is True, f"source no ok: {h['source']}")
        engines = ",".join(f"{k}({'ok' if v.get('configured') else 'no'})" for k, v in h["engines"].items())
        return (f"status={h.get('status')} contract={h['contract']} voice_modes={h['voice_modes']} "
                f"engines={engines or 'ninguno'} source_ms={h['source'].get('ms')}")

    def check_cors(self) -> str:
        if not self.origin:
            raise Skip("sin --origin")
        r = self.http.options("/sessions", headers={
            "Origin": self.origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-session-token"})
        allowed = r.headers.get("access-control-allow-origin")
        expect(r.status_code in (200, 204), f"HTTP {r.status_code}: {r.text[:120]}")
        expect(allowed in (self.origin, "*"), f"allow-origin={allowed!r}")
        hdrs = (r.headers.get("access-control-allow-headers") or "").lower()
        expect("x-session-token" in hdrs, f"allow-headers sin x-session-token: {hdrs!r}")
        return f"allow-origin={allowed}"

    def check_session(self) -> str:
        r = self.http.post("/sessions", json={"locale": "es-CO"})
        expect(r.status_code == 201, f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        token = body.get("token")
        expect(isinstance(token, str) and len(token) > 10, "sin token")
        self.token = token
        return f"token presente (len={len(token)}) expires_at={body.get('expires_at')}"

    def check_unauthorized(self) -> str:
        r = self.http.get("/dataset/brief")
        expect(r.status_code == 401, f"HTTP {r.status_code} (esperado 401)")
        expect(self._error_shape(r), f"formato de error inválido: {r.text[:200]}")
        bad = self.http.get("/dataset/brief", headers={"X-Session-Token": "x.y.z"})
        expect(bad.status_code == 401, f"token falso -> HTTP {bad.status_code}")
        return f"code={r.json()['error']['code']}"

    def check_brief(self) -> str:
        r = self.http.get("/dataset/brief", headers=self.headers())
        expect(r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
        b = r.json()
        s = b.get("stats", {})
        for k in ("providers", "site_codes", "rows"):
            expect(s.get(k) == GOLDEN[k], f"stats.{k}={s.get(k)} (esperado {GOLDEN[k]})")
        nature = {i.get("key"): i.get("value") for i in b.get("by_nature", [])}
        expect(nature == GOLDEN_NATURE, f"by_nature={nature}")
        return f"providers={s['providers']} site_codes={s['site_codes']} rows={s['rows']} cache={s.get('cache_status')}"

    def check_provider_count(self) -> str:
        env = self.tool("aggregate_ips", {"metric": "provider_count"}, force_live=True)
        expect(env.get("status") == "ok", f"status={env.get('status')} error={env.get('error')}")
        expect(env.get("data", {}).get("value") == GOLDEN["providers"], f"value={env.get('data', {}).get('value')}")
        ev = env.get("evidence") or {}
        expect(bool(ev.get("query_fingerprint")) and ev.get("dataset_id"), "evidence incompleta")
        expect(bool((env.get("trace") or {}).get("soql")), "trace.soql vacío")
        cache = env["trace"].get("cache_status")
        expect(cache == "live", f"trace.cache_status={cache} (esperado live con force_live)")
        return f"value=9320 cache={cache} source_ms={env['trace'].get('ms')}"

    def check_beds(self) -> str:
        env = self.tool("aggregate_ips", {"metric": "capacity_sum", "filters": {"capacity_group": "CAMAS"}})
        expect(env.get("status") == "ok", f"status={env.get('status')} error={env.get('error')}")
        value = env["data"].get("value")
        expect(value == GOLDEN["beds"], f"value={value} (esperado {GOLDEN['beds']})")
        return f"value={value} unit={env['data'].get('unit')}"

    def check_group_nature(self) -> str:
        env = self.tool("aggregate_ips", {"metric": "provider_count", "group_by": "nature"})
        expect(env.get("status") == "ok", f"status={env.get('status')} error={env.get('error')}")
        groups = {g.get("key"): g.get("value") for g in env["data"].get("groups", [])}
        expect(groups == GOLDEN_NATURE, f"groups={groups}")
        return json.dumps(groups, ensure_ascii=False)

    def check_search(self) -> str:
        env = self.tool("search_ips", {"department": "Antioquia", "nature": "Pública"})
        expect(env.get("status") == "ok", f"status={env.get('status')} error={env.get('error')}")
        items = env["data"].get("items", [])
        expect(items and all(i.get("site_key") for i in items), "items sin site_key")
        expect(all(i.get("nature") == "Pública" for i in items), "naturaleza distinta de Pública")
        return f"items={len(items)} next_cursor={'sí' if env.get('next_cursor') else 'no'}"

    def check_homonym(self) -> str:
        env = self.tool("aggregate_ips", {"metric": "provider_count", "filters": {"municipality": "Armenia"}})
        expect(env.get("status") == "ambiguous", f"status={env.get('status')}")
        cands = env["data"].get("candidates", [])
        expect(len(cands) >= 2, f"candidates={cands}")
        return f"candidates={len(cands)}"

    def check_correct_context(self) -> str:
        env = self.tool("correct_context", {"target_turn_id": "smoke-t1", "expected_state_version": 3,
                                            "field": "department", "value": "Antioquia"}, state_version=3)
        expect(env.get("status") == "ok", f"status={env.get('status')} error={env.get('error')}")
        expect(env.get("state_version") == 4, f"state_version={env.get('state_version')} (esperado 4)")
        expect(env.get("context_patch", {}).get("state_version") == 4, "context_patch.state_version != 4")
        stale = self.tool("correct_context", {"target_turn_id": "smoke-t1", "expected_state_version": 2,
                                              "field": "department", "value": "Antioquia"}, state_version=3)
        expect(stale.get("status") == "invalid" and (stale.get("error") or {}).get("code") == "STATE_CONFLICT",
               f"versión vieja -> status={stale.get('status')} error={stale.get('error')}")
        return "3 -> 4; versión vieja -> STATE_CONFLICT"

    def check_idempotency(self) -> str:
        call_id = str(uuid.uuid4())
        args = {"metric": "site_count", "group_by": "nature"}
        a = self.tool("aggregate_ips", args, call_id=call_id, state_version=7)
        b = self.tool("aggregate_ips", args, call_id=call_id, state_version=7)
        expect(a.get("status") == "ok", f"status={a.get('status')}")
        expect(a == b, "dos respuestas distintas para el mismo tool_call_id + state_version")
        return f"idénticas (fingerprint {a['evidence']['query_fingerprint'][:19]}...)"

    def check_unknown_tool(self) -> str:
        r = self.post("/tools/drop_table", {"tool_call_id": str(uuid.uuid4()), "args": {}})
        expect(r.status_code == 404, f"HTTP {r.status_code}")
        expect(self._error_shape(r), f"formato de error inválido: {r.text[:200]}")
        return f"code={r.json()['error']['code']}"

    def _configured_engines(self) -> list[str]:
        return [k for k, v in (self.health.get("engines") or {}).items() if v.get("configured")]

    def check_engine(self, engine: str, voice_mode: str = "engine") -> Callable[[], str]:
        def _check() -> str:
            if self.skip_engines:
                raise Skip("--skip-engines")
            if engine not in self._configured_engines():
                raise Skip(f"{engine} no configurado en /health")
            if voice_mode == "cloned" and "cloned" not in (self.health.get("voice_modes") or []):
                raise Skip("/health no ofrece voz clonada")
            r = self.post("/realtime/session", {"engine": engine, "conversation_id": "smoke", "voice_mode": voice_mode})
            expect(r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
            s = r.json()
            connect = s.get("connect") or {}
            expect(bool(connect.get("url")), "sin connect.url")
            expect(bool(connect.get("token")), "sin connect.token")
            expect(bool(s.get("model")), "sin model")
            effective = (s.get("config") or {}).get("voice_mode")
            if voice_mode == "cloned":
                supports = (self.health["engines"][engine] or {}).get("supports_cloned")
                want = "cloned" if supports else "engine"
                expect(effective == want, f"config.voice_mode={effective} (esperado {want})")
            return (f"model={s['model']} voice_mode={effective} token(len={len(connect['token'])}) "
                    f"expires_at={connect.get('expires_at')}")
        return _check

    def check_speech(self) -> str:
        if self.skip_engines:
            raise Skip("--skip-engines")
        if "cloned" not in (self.health.get("voice_modes") or []):
            raise Skip("/health no ofrece voz clonada")
        r = self.post("/speech/session", {"conversation_id": "smoke"})
        expect(r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
        s = r.json()
        expect(bool((s.get("connect") or {}).get("url")), "sin connect.url")
        return f"synth={s.get('synth')} model={s.get('model')} token(len={len(s['connect'].get('token') or '')})"

    def check_analysis(self) -> str:
        r = self.post("/analysis/utterance", {"turn_id": "t1", "text": "me estás confundiendo, sé más directo"})
        expect(r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        affect, style = body.get("affect") or {}, body.get("style") or {}
        expect(bool(affect.get("sentiment")), "sin affect.sentiment")
        expect(style.get("style") == "directo", f"style={style.get('style')} (esperado directo)")
        expect(style.get("source") == "preference", f"style.source={style.get('source')} (esperado preference)")
        return (f"sentiment={affect['sentiment']} emotion={affect.get('emotion')} method={affect.get('method')} "
                f"style={style['style']}/{style['source']} ms={body.get('ms')}")

    def check_feedback(self) -> str:
        r = self.post("/feedback", {"turn_id": "t1", "kind": "tone", "text": "smoke", "category": "TONE"})
        expect(r.status_code == 202, f"HTTP {r.status_code}: {r.text[:200]}")
        return "202"

    def check_web(self) -> str:
        if not self.web_url:
            raise Skip("sin --web-url")
        r = httpx.get(self.web_url, timeout=TIMEOUT_S, follow_redirects=True)
        expect(r.status_code == 200, f"HTTP {r.status_code}")
        text = r.text.lower()
        expect("inteligencia artificial" in text or " ia " in text or "asistente de ia" in text,
               "no encuentro el aviso de IA en el HTML")
        return "200 con aviso de IA"

    # -- driver ---------------------------------------------------------------

    def all(self) -> int:
        print(f"Smoke público contra {self.base}\n")
        self.run("GET /health", self.check_health)
        self.run("CORS preflight", self.check_cors)
        self.run("POST /sessions", self.check_session)
        self.run("401 sin token", self.check_unauthorized)
        self.run("GET /dataset/brief (números dorados)", self.check_brief)
        self.run("aggregate provider_count (live)", self.check_provider_count)
        self.run("aggregate capacity_sum CAMAS", self.check_beds)
        self.run("aggregate group_by nature", self.check_group_nature)
        self.run("search_ips Antioquia Pública", self.check_search)
        self.run("aggregate Armenia -> ambiguous", self.check_homonym)
        self.run("correct_context state_version+1", self.check_correct_context)
        self.run("idempotencia tool_call_id", self.check_idempotency)
        self.run("herramienta desconocida -> 404", self.check_unknown_tool)
        for engine in ("openai", "gemini"):
            self.run(f"POST /realtime/session {engine}", self.check_engine(engine))
            self.run(f"POST /realtime/session {engine} cloned", self.check_engine(engine, "cloned"))
        self.run("POST /speech/session", self.check_speech)
        self.run("POST /analysis/utterance", self.check_analysis)
        self.run("POST /feedback", self.check_feedback)
        self.run("GET / del web (aviso IA)", self.check_web, priority="P1")
        self.http.close()
        return self.summary()

    def summary(self) -> int:
        print("\n| check | ms | resultado |\n|---|---:|---|")
        for r in self.results:
            print(f"| {r.priority} {r.name} | {r.ms} | {r.outcome} |")
        failed = [r for r in self.results if r.outcome == "FAIL" and r.priority == "P0"]
        counts = {o: sum(r.outcome == o for r in self.results) for o in ("PASS", "FAIL", "SKIP")}
        print(f"\nPASS {counts['PASS']} · FAIL {counts['FAIL']} · SKIP {counts['SKIP']}"
              f" -> {'ROJO' if failed else 'VERDE'}")
        return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Smoke test de la API pública del Reto 01 (docs/11 §7)")
    p.add_argument("--base-url", required=True, help="URL de la API, p. ej. https://api.example.app")
    p.add_argument("--origin", help="Origen del web para probar el preflight CORS")
    p.add_argument("--web-url", help="URL del web para verificar 200 y el aviso de IA (P1)")
    p.add_argument("--skip-engines", action="store_true", help="No emitir credenciales de motores ni de voz")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
    return Smoke(a.base_url, a.origin, a.web_url, a.skip_engines).all()


if __name__ == "__main__":
    sys.exit(main())
