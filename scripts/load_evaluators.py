"""Carga de varios evaluadores del jurado a la vez contra la API de Reto 01.

Simula N evaluadores simultáneos (asyncio) y comprueba aislamiento, límites de
tasa, credenciales de motor, voz clonada (Cartesia) y la fuente datos.gov.co.
No imprime secretos ni tokens: solo longitudes y conteos.

    python scripts/load_evaluators.py --base-url http://127.0.0.1:8200 --users 8
    python scripts/load_evaluators.py --base-url https://<api> --no-engines --no-cartesia

Opciones caras o agresivas van apagadas por omisión en URLs públicas:
``--engines`` (3 conversaciones de texto con OpenAI Realtime, centavos),
``--cartesia`` (N síntesis cortas, ~150 créditos cada una) e ``--ip-exhaust``
(agota el límite por IP durante 60 s: **nunca** contra producción en el jurado).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import re
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

DEPARTMENTS = ["Antioquia", "Santander", "Bogotá D.C", "Valle del Cauca", "Caldas", "Boyacá",
               "Nariño", "Tolima", "Cundinamarca", "Risaralda", "Meta", "Cauca"]
BASELINE_DEPT = "Huila"
GOLDEN = {"providers": 9320, "public": 998, "beds": 97036}
TEXTS = [
    "Estoy muy molesto, llevo media hora esperando y nadie me responde.",
    "Gracias, eso me sirve muchísimo, qué bien.",
    "No entiendo bien, ¿me lo puedes repetir más despacio?",
    "Necesito el dato ya, es urgente para un informe.",
    "Hola, quisiera saber cuántas IPS hay en mi departamento.",
    "Esto es confuso, no sé si la cifra es correcta.",
    "Perfecto, muy claro, sigamos.",
    "Me preocupa que no haya camas suficientes en mi municipio.",
]


@dataclass
class Sample:
    route: str
    ms: float
    status: int
    phase: str
    cache: str | None = None
    code: str | None = None
    message: str | None = None


@dataclass
class Report:
    samples: list[Sample] = field(default_factory=list)
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def check(self, name: str, ok: bool, **numbers: Any) -> None:
        self.checks[name] = {"result": "PASS" if ok else "FAIL", **numbers}
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {json.dumps(numbers, ensure_ascii=False, default=str)}")


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))
    return round(s[k], 1)


def digits(text: str) -> set[int]:
    """Numbers said in a text: '9.320', '9 320', '97036' -> ints."""
    found = set()
    for m in re.finditer(r"\d{1,3}(?:[.\s ]\d{3})+|\d+", text):
        try:
            found.add(int(re.sub(r"[.\s ]", "", m.group())))
        except ValueError:
            pass
    return found


class Client:
    """One evaluator: own session token, own X-Forwarded-For (simulated public IP)."""

    def __init__(self, http: httpx.AsyncClient, rep: Report, phase: str, ip: str | None = None) -> None:
        self.http, self.rep, self.phase, self.ip = http, rep, phase, ip
        self.token = ""
        self.sid = ""

    def headers(self) -> dict[str, str]:
        h = {"X-Session-Token": self.token} if self.token else {}
        if self.ip:
            h["X-Forwarded-For"] = self.ip
        return h

    async def call(self, method: str, path: str, **kw: Any) -> tuple[int, Any]:
        t0 = time.perf_counter()
        r = await self.http.request(method, path, headers=self.headers(), **kw)
        ms = (time.perf_counter() - t0) * 1000
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:200]}
        cache = body.get("evidence", {}).get("cache_status") if isinstance(body, dict) else None
        if isinstance(body, dict) and isinstance(body.get("trace"), dict) and not body["trace"].get("soql"):
            cache = "no_query"  # correct_context / invalid: nothing was asked to the source
        code = body.get("error", {}).get("code") if isinstance(body, dict) and isinstance(body.get("error"), dict) else None
        route = "/tools" if path.startswith("/tools/") else path.split("?")[0]
        msg = body["error"].get("message") if code else None  # exception names only, never secrets
        self.rep.samples.append(Sample(route, ms, r.status_code, self.phase, cache, code, msg))
        return r.status_code, body

    async def start(self) -> None:
        st, body = await self.call("POST", "/sessions", json={"locale": "es-CO"})
        assert st == 201, (st, body)
        self.token = body["token"]
        claims = self.token.split(".")[0]
        self.sid = json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))["sid"]

    async def tool(self, name: str, call_id: str, turn: str, args: dict, *, state_version: int = 0,
                   force_live: bool = False) -> dict:
        st, env = await self.call("POST", f"/tools/{name}", json={
            "tool_call_id": call_id, "turn_id": turn, "args": args, "force_live": force_live,
            "context": {"conversation_id": f"conv-{self.sid}", "turn_id": turn, "state_version": state_version}})
        env["_http"] = st
        return env


# ---------------------------------------------------------------------------
# Check 1 + 5: isolation and datos.gov.co under load
# ---------------------------------------------------------------------------

def plan_for(i: int, dept: str) -> list[tuple[str, str, dict, int]]:
    """Five DIFFERENT tool calls per evaluator; call ids repeat across evaluators on purpose."""
    return [
        ("aggregate_ips", "call_1", {"metric": "provider_count", "filters": {"department": dept}}, 0),
        ("aggregate_ips", "call_2", {"metric": "capacity_sum", "filters": {"department": dept, "capacity_group": "CAMAS"}}, 0),
        ("search_ips", "call_3", {"department": dept, "nature": "Pública", "limit": 3}, 0),
        ("aggregate_ips", "call_4", {"metric": "provider_count", "group_by": "nature", "filters": {"department": dept}}, 0),
        ("correct_context", "call_5", {"field": "nature", "value": ["Pública", "Privada", "Mixta"][i % 3]}, i),
    ]


async def run_plan(c: Client, i: int, dept: str, force_live: bool) -> list[dict]:
    out = []
    for k, (name, cid, args, sv) in enumerate(plan_for(i, dept)):
        env = await c.tool(name, cid, f"u{i}-t{k}", args, state_version=sv, force_live=force_live)
        env["_req"] = {"name": name, "call_id": cid, "turn": f"u{i}-t{k}", "args": args, "sv": sv}
        out.append(env)
    # A details call on the first site found (depends on call_3).
    items = out[2].get("data", {}).get("items") or []
    if items:
        env = await c.tool("get_ips_details", "call_6", f"u{i}-t5", {"site_key": items[0]["site_key"],
                                                                      "capacity_group": "CAMAS"}, force_live=force_live)
        env["_req"] = {"name": "get_ips_details", "call_id": "call_6", "turn": f"u{i}-t5",
                       "args": {"site_key": items[0]["site_key"]}, "sv": 0}
        out.append(env)
    return out


def own_problems(i: int, dept: str, envs: list[dict]) -> list[str]:
    """Does every envelope answer *this* evaluator's request?"""
    errs = []
    for env in envs:
        req = env["_req"]
        tag = f"u{i}:{req['call_id']}"
        if env.get("_http") != 200:
            errs.append(f"{tag} HTTP {env.get('_http')} {env.get('error')}")
            continue
        if env.get("tool_call_id") != req["call_id"]:
            errs.append(f"{tag} tool_call_id={env.get('tool_call_id')}")
        if env.get("turn_id") != req["turn"]:
            errs.append(f"{tag} turn_id echo {env.get('turn_id')} != {req['turn']}")
        f = env.get("evidence", {}).get("filters", {})
        if req["name"] in ("aggregate_ips", "search_ips") and env.get("status") in ("ok", "empty"):
            if f.get("department") is None or dept.split()[0].lower()[:4] not in str(f.get("department")).lower():
                errs.append(f"{tag} filtros de otro: {f}")
        if req["name"] == "get_ips_details" and f.get("site_key") != req["args"]["site_key"]:
            errs.append(f"{tag} site_key ajeno {f.get('site_key')}")
        if req["name"] == "correct_context":
            if env.get("state_version") != req["sv"] + 1:
                errs.append(f"{tag} state_version {env.get('state_version')} != {req['sv'] + 1}")
            if f.get("nature") != req["args"]["value"]:
                errs.append(f"{tag} corrección ajena {f}")
    return errs


def comparable(env: dict) -> Any:
    return {"status": env.get("status"), "data": env.get("data"), "filters": env.get("evidence", {}).get("filters")}


async def check_isolation(base: str, n: int, rep: Report) -> None:
    depts = DEPARTMENTS[:n] if n <= len(DEPARTMENTS) else (DEPARTMENTS * (n // len(DEPARTMENTS) + 1))[:n]
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=100)
    async with httpx.AsyncClient(base_url=base, timeout=30, limits=limits) as http:
        # Baseline: one evaluator alone (live, so it measures the source and not the cache).
        solo = Client(http, rep, "solo", ip="198.51.100.1")
        await solo.start()
        await run_plan(solo, 99, BASELINE_DEPT, force_live=True)

        # N evaluators at once, all from the same simulated venue IP.
        users = [Client(http, rep, "concurrent", ip="198.51.100.2") for _ in range(n)]
        await asyncio.gather(*(u.start() for u in users))
        tokens = {u.token for u in users}
        sids = {u.sid for u in users}

        async def flow(i: int, u: Client) -> dict:
            st, brief = await u.call("GET", "/dataset/brief")
            envs = await run_plan(u, i, depts[i], force_live=True)
            text = TEXTS[i % len(TEXTS)]
            st_a, an = await u.call("POST", "/analysis/utterance", json={
                "turn_id": f"u{i}-a", "text": text, "turn_index": i, "state_version": 0})
            value = envs[0].get("data", {}).get("value")
            st_v, ver = await u.call("POST", "/verify/answer", json={
                "turn_id": f"u{i}-v", "text": f"En {depts[i]} hay {value} prestadores.",
                "tool_results": [envs[0]]})
            return {"brief": (st, brief), "envs": envs, "analysis": (st_a, an), "verify": (st_v, ver), "value": value}

        t0 = time.perf_counter()
        results = await asyncio.gather(*(flow(i, u) for i, u in enumerate(users)))
        wall = time.perf_counter() - t0

        # Second wave, normal use (no force_live): measures the shared cache.
        users2 = [Client(http, rep, "cached", ip="198.51.100.3") for _ in range(n)]
        await asyncio.gather(*(u.start() for u in users2))
        results2 = await asyncio.gather(*(run_plan(u, i, depts[i], force_live=False) for i, u in enumerate(users2)))

        # Reference: the same plan, sequentially, by fresh sessions (ground truth per evaluator).
        refs = []
        for i in range(n):
            r = Client(http, rep, "reference", ip="198.51.100.4")
            await r.start()
            refs.append(await run_plan(r, i, depts[i], force_live=False))

        # Same evaluator retries call_1 (same state): idempotent, same result, no new query.
        st_retry = await users[0].tool("aggregate_ips", "call_1", "u0-t0",
                                       {"metric": "provider_count", "filters": {"department": depts[0]}})
        # Same session, same call id, DIFFERENT args: what does idempotency do? (not cross-user)
        same_id_other_args = await users[0].tool("aggregate_ips", "call_1", "u0-t9",
                                                 {"metric": "provider_count", "filters": {"department": depts[1]}})

        # Tampered token: B's sid with A's signature -> must be 401.
        a, b = users[0], users[1]
        claims_b = b.token.split(".")[0]
        forged = Client(http, rep, "forged", ip="198.51.100.5")
        forged.token = claims_b + "." + a.token.split(".")[1]
        st_forged, _ = await forged.call("POST", "/verify/answer", json={"turn_id": "x", "text": "1"})
        forged.token = "a.b"
        st_bad, _ = await forged.call("GET", "/dataset/brief")
        forged.token = ""
        st_none, _ = await forged.call("GET", "/dataset/brief")

    problems, mismatches, mismatches2 = [], [], []
    an_ok = ver_ok = brief_ok = 0
    for i, res in enumerate(results):
        problems += own_problems(i, depts[i], res["envs"])
        problems += own_problems(i, depts[i], results2[i])
        for e, r in zip(res["envs"], refs[i]):
            if comparable(e) != comparable(r):
                mismatches.append(f"u{i}:{e['_req']['call_id']}")
        for e, r in zip(results2[i], refs[i]):
            if comparable(e) != comparable(r):
                mismatches2.append(f"u{i}:{e['_req']['call_id']}")
        st, br = res["brief"]
        brief_ok += st == 200 and br.get("stats", {}).get("providers") == GOLDEN["providers"]
        st_a, an = res["analysis"]
        an_ok += st_a == 200 and an.get("affect", {}).get("turn_id") == f"u{i}-a"
        st_v, ver = res["verify"]
        ver_ok += st_v == 200 and ver.get("turn_id") == f"u{i}-v" and ver.get("grounded") is True
    values = [res["value"] for res in results]
    call1_distinct = len(set(values))
    ref_distinct = len({r[0].get("data", {}).get("value") for r in refs})  # real ties exist (Boyacá = Tolima = 312)
    # Data really differs across evaluators (if idempotency were global, all call_1 would be equal).
    rep.check("1a aislamiento HTTP (respuestas propias, eco de turn_id/filtros)",
              not problems and not mismatches and not mismatches2 and len(tokens) == n and len(sids) == n
              and call1_distinct == ref_distinct,
              users=n, tokens_distintos=len(tokens), longitud_token=len(users[0].token),
              call_1_valores_distintos=call1_distinct, distintos_en_referencia=ref_distinct, call_1_valores=values,
              problemas=problems[:10], difiere_de_referencia=mismatches[:10],
              difiere_de_referencia_cache=mismatches2[:10], wall_s=round(wall, 2))
    rep.check("1b brief / analista / verificación por evaluador", brief_ok == n and an_ok == n and ver_ok == n,
              brief_ok=brief_ok, analysis_turn_id_ok=an_ok, verify_grounded_ok=ver_ok)
    rep.check("1c token ajeno o adulterado no sirve", st_forged == 401 and st_bad == 401 and st_none == 401,
              sid_de_B_con_firma_de_A=st_forged, token_basura=st_bad, sin_token=st_none)
    reused = st_retry.get("data") == results[0]["envs"][0].get("data") and st_retry.get("turn_id") == "u0-t0"
    leaked = same_id_other_args.get("data") == results[0]["envs"][0].get("data")
    rep.check("1d idempotencia por sesión (mismo call_id, mismo estado)", reused,
              reintento_igual=reused,
              mismo_call_id_otros_args_devuelve_resultado_viejo=leaked,
              valor_devuelto=same_id_other_args.get("data", {}).get("value"),
              filtros_devueltos=same_id_other_args.get("evidence", {}).get("filters"))
    if leaked:
        rep.issues.append("IDEMPOTENCIA: en la MISMA sesión, el mismo tool_call_id+state_version con otros args "
                          "devuelve el sobre anterior (clave sin nombre ni args). No cruza usuarios.")

    def lat(phase: str) -> list[float]:
        return [s.ms for s in rep.samples if s.phase == phase and s.route == "/tools" and s.status == 200]
    solo_l, conc_l = lat("solo"), lat("concurrent")
    p95_s, p95_c = pct(solo_l, 95), pct(conc_l, 95)
    rep.check("1e latencia /tools (live) 1 vs N", bool(conc_l) and p95_c is not None and p95_c < 6000,
              solo_n=len(solo_l), solo_p50=pct(solo_l, 50), solo_p95=p95_s,
              concurrente_n=len(conc_l), concurrente_p50=pct(conc_l, 50), concurrente_p95=p95_c,
              cached_p50=pct(lat("cached"), 50), cached_p95=pct(lat("cached"), 95))

    # Check 5: datos.gov.co under load.
    tool_samples = [s for s in rep.samples if s.route == "/tools" and s.phase in ("solo", "concurrent", "cached", "reference")]
    unavailable = [s for s in tool_samples if s.code in ("TIMEOUT", "RATE_LIMITED", "SOURCE_REJECTED", "SOURCE_UNAVAILABLE")]
    statuses = {}
    for res in results:
        for e in res["envs"]:
            statuses[e.get("status")] = statuses.get(e.get("status"), 0) + 1
    by_phase = {}
    for s in tool_samples:
        by_phase.setdefault(s.phase, {}).setdefault(s.cache or "none", 0)
        by_phase[s.phase][s.cache or "none"] += 1
    envs_unavailable = sum(1 for res in results for e in res["envs"] if e.get("status") == "unavailable")
    envs_unavailable += sum(1 for envs in results2 for e in envs if e.get("status") == "unavailable")
    rep.check("5 datos.gov.co con N usuarios", envs_unavailable == 0 and not unavailable,
              estados_ola_live=statuses, unavailable=envs_unavailable,
              errores_fuente=[(s.code, s.status) for s in unavailable][:10], cache_por_fase=by_phase)


# ---------------------------------------------------------------------------
# Check 2: rate limits from one shared IP
# ---------------------------------------------------------------------------

async def check_rate_limits(base: str, n: int, rep: Report, ip_exhaust: bool, seconds: int = 20) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=30,
                                 limits=httpx.Limits(max_connections=200)) as http:
        venue = "198.51.100.10"
        users = [Client(http, rep, "rl-normal", ip=venue) for _ in range(n)]
        abuser = Client(http, rep, "rl-abuser", ip=venue)
        await asyncio.gather(*(u.start() for u in users), abuser.start())

        async def normal(i: int, u: Client) -> list[int]:
            codes = []
            for k in range(seconds):
                t0 = time.perf_counter()
                if k % 5 == 0:
                    st, _ = await u.call("GET", "/dataset/brief")
                else:
                    st, _ = await u.call("POST", "/verify/answer", json={"turn_id": f"rl{i}-{k}", "text": "9.320"})
                codes.append(st)
                await asyncio.sleep(max(0.0, 1.0 - (time.perf_counter() - t0)))
            return codes

        async def abuse() -> list[int]:
            async def one(k: int) -> int:
                await asyncio.sleep(k * (seconds * 0.6 / 200))  # 200 requests in ~12 s (> 200/min)
                st, _ = await abuser.call("POST", "/verify/answer", json={"turn_id": f"ab{k}", "text": "1"})
                return st
            return await asyncio.gather(*(one(k) for k in range(200)))

        res = await asyncio.gather(abuse(), *(normal(i, u) for i, u in enumerate(users)))
        ab, normals = res[0], res[1:]
        normal_429 = sum(c == 429 for codes in normals for c in codes)
        normal_ok = sum(c == 200 for codes in normals for c in codes)
        ab_429, ab_ok = sum(c == 429 for c in ab), sum(c == 200 for c in ab)
        rep.check("2a mismo IP: N evaluadores a ~1 req/s + 1 abusivo (200 req en ~12 s)",
                  normal_429 == 0 and ab_429 > 0,
                  normales_ok=normal_ok, normales_429=normal_429, abusivo_ok=ab_ok, abusivo_429=ab_429)

        if not ip_exhaust:
            return
        # The abuser rotates sessions (POST /sessions has no limit) and drains the shared IP bucket.
        venue2 = f"10.20.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"  # fresh bucket per run
        victim = Client(http, rep, "rl-victim", ip=venue2)
        await victim.start()
        sem = asyncio.Semaphore(50)
        rotated: list[int] = []

        async def burst(cl: Client, k: int) -> None:
            async with sem:
                st, _ = await cl.call("POST", "/verify/answer", json={"turn_id": f"x{k}", "text": "1"})
                rotated.append(st)
        t0 = time.perf_counter()
        sessions = 0
        for chunk in range(14):
            cl = Client(http, rep, "rl-rotator", ip=venue2)
            await cl.start()
            sessions += 1
            await asyncio.gather(*(burst(cl, chunk * 115 + k) for k in range(115)))
        st_victim, body = await victim.call("POST", "/verify/answer", json={"turn_id": "v", "text": "1"})
        other_ip = Client(http, rep, "rl-victim", ip="198.51.100.21")
        await other_ip.start()
        st_other, _ = await other_ip.call("POST", "/verify/answer", json={"turn_id": "v", "text": "1"})
        rep.check("2b abusivo que rota sesiones agota el cupo por IP (informativo)",
                  st_victim != 429,
                  sesiones_rotadas=sessions, peticiones=len(rotated), ok_200=rotated.count(200),
                  r429=rotated.count(429), s=round(time.perf_counter() - t0, 1),
                  evaluador_mismo_ip=st_victim, evaluador_otro_ip=st_other)
        if st_victim == 429:
            rep.issues.append("RATE LIMIT: POST /sessions no tiene límite; rotando sesiones un abusivo agota el cupo "
                              "por IP (1500/min) y deja en 429 a todos los evaluadores de la misma red durante 60 s.")


# ---------------------------------------------------------------------------
# Check 3: engine credentials and 3 simultaneous OpenAI text conversations
# ---------------------------------------------------------------------------

QUESTIONS = [
    ("¿Cuántos prestadores de salud hay en total en el registro? Responde con la cifra.", GOLDEN["providers"]),
    ("¿Cuántas camas hay en total en el país, sumando todos los tipos de cama? Responde con la cifra.", GOLDEN["beds"]),
    ("¿Cuántas IPS públicas hay en total? Responde con la cifra.", GOLDEN["public"]),
]


async def openai_conversation(base: str, rep: Report, idx: int, question: str) -> dict:
    import websockets

    out: dict[str, Any] = {"q": idx, "tools": [], "text": "", "error": None}
    async with httpx.AsyncClient(base_url=base, timeout=30) as http:
        c = Client(http, rep, "engine", ip=f"198.51.100.{30 + idx}")
        await c.start()
        st, sess = await c.call("POST", "/realtime/session", json={
            "engine": "openai", "conversation_id": f"load-{idx}-{uuid.uuid4().hex[:6]}", "voice_mode": "cloned"})
        if st != 200:
            out["error"] = f"mint HTTP {st} {sess.get('error')}"
            return out
        out["voice_mode"] = sess["config"].get("voice_mode")
        t0 = time.perf_counter()
        async with websockets.connect(sess["connect"]["url"], subprotocols=sess["connect"]["protocols"],
                                      max_size=None, open_timeout=15) as ws:
            await ws.send(json.dumps({"type": "session.update", "session": {"type": "realtime",
                                                                           "output_modalities": ["text"]}}))
            await ws.send(json.dumps({"type": "conversation.item.create", "item": {
                "type": "message", "role": "user", "content": [{"type": "input_text", "text": question}]}}))
            await ws.send(json.dumps({"type": "response.create"}))
            rounds = 0
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.monotonic())))
                if msg.get("type") == "error":
                    out["error"] = msg.get("error", {}).get("message")
                    if "session" not in str(out["error"]).lower():
                        break
                if msg.get("type") != "response.done":
                    continue
                resp = msg.get("response", {})
                calls = [o for o in resp.get("output", []) if o.get("type") == "function_call"]
                for o in resp.get("output", []):
                    if o.get("type") == "message":
                        for part in o.get("content", []):
                            out["text"] += part.get("text") or part.get("transcript") or ""
                if not calls or rounds >= 3:
                    if resp.get("status") not in ("completed", None):
                        out["error"] = f"response {resp.get('status')} {resp.get('status_details')}"
                    break
                rounds += 1
                for call in calls:
                    args = json.loads(call.get("arguments") or "{}")
                    env = await c.tool(call["name"], call["call_id"], f"e{idx}-r{rounds}", args)
                    out["tools"].append({"name": call["name"], "args": args, "status": env.get("status"),
                                         "value": env.get("data", {}).get("value"),
                                         "groups": env.get("data", {}).get("groups")})
                    await ws.send(json.dumps({"type": "conversation.item.create", "item": {
                        "type": "function_call_output", "call_id": call["call_id"],
                        "output": env.get("for_model") or json.dumps(env.get("data"))}}))
                await ws.send(json.dumps({"type": "response.create"}))
        out["s"] = round(time.perf_counter() - t0, 2)
    return out


async def check_engines(base: str, rep: Report) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=30) as http:
        c = Client(http, rep, "mint", ip="198.51.100.40")
        await c.start()

        async def mint(engine: str, k: int) -> tuple[str, int, str]:
            st, body = await c.call("POST", "/realtime/session", json={
                "engine": engine, "conversation_id": f"mint-{engine}-{k}"})
            tok = body.get("connect", {}).get("token", "") if st == 200 else ""
            return engine, st, tok if st == 200 else f"{body.get('error', {}).get('message')}"
        t0 = time.perf_counter()
        mints = await asyncio.gather(*(mint(e, k) for e in ("openai", "gemini") for k in range(5)))
        wall = time.perf_counter() - t0
    by = {}
    for e, st, tok in mints:
        d = by.setdefault(e, {"ok": 0, "codes": [], "tokens": set(), "len": 0, "errors": []})
        d["codes"].append(st)
        if st != 200:
            d["errors"].append(tok)  # the error message (exception name), not a token
        elif tok:
            d["ok"] += 1
            d["tokens"].add(hashlib.sha256(tok.encode()).hexdigest())
            d["len"] = len(tok)
    summary = {e: {"ok": d["ok"], "codes": d["codes"], "distintos": len(d["tokens"]), "longitud": d["len"],
                   "errores": d["errors"]}
               for e, d in by.items()}
    rep.check("3a credenciales concurrentes (5 OpenAI + 5 Gemini)",
              all(d["ok"] == 5 and len(d["tokens"]) == 5 for d in by.values()),
              wall_s=round(wall, 2), **summary)

    convs = await asyncio.gather(*(openai_conversation(base, rep, i, q) for i, (q, _) in enumerate(QUESTIONS)),
                                 return_exceptions=True)
    rows, ok = [], 0
    for i, conv in enumerate(convs):
        expected = QUESTIONS[i][1]
        others = {v for j, (_, v) in enumerate(QUESTIONS) if j != i}
        if isinstance(conv, Exception):
            rows.append({"q": i, "error": repr(conv)[:200]})
            continue
        said = digits(conv["text"])
        good = expected in said and not (said & others)
        ok += good
        rows.append({"q": i, "esperado": expected, "ok": good, "s": conv.get("s"), "voice_mode": conv.get("voice_mode"),
                     "tools": conv["tools"], "respuesta": conv["text"][:300], "error": conv.get("error")})
    rep.check("3b 3 conversaciones OpenAI Realtime simultáneas (texto) con /tools propio",
              ok == len(QUESTIONS), correctas=ok, detalle=rows)


# ---------------------------------------------------------------------------
# Check 4: Cartesia cloned voice concurrency
# ---------------------------------------------------------------------------

SENTENCE = ("Hola, soy el asistente de datos de salud. Según el registro del Ministerio, con corte a "
            "noviembre de dos mil veintidós, hay nueve mil trescientos veinte prestadores.")


async def check_cartesia(base: str, rep: Report, n: int) -> None:
    import websockets

    async with httpx.AsyncClient(base_url=base, timeout=30) as http:
        users = [Client(http, rep, "speech", ip="198.51.100.50") for _ in range(n)]
        await asyncio.gather(*(u.start() for u in users))
        t0 = time.perf_counter()
        minted = await asyncio.gather(*(u.call("POST", "/speech/session", json={"conversation_id": f"sp-{k}"})
                                        for k, u in enumerate(users)))
        mint_s = time.perf_counter() - t0
    codes = [st for st, _ in minted]
    toks = {hashlib.sha256(b["connect"]["token"].encode()).hexdigest() for st, b in minted if st == 200}
    sessions = [b for st, b in minted if st == 200]
    if not sessions:
        rep.check("4 Cartesia voz clonada concurrente", False, mint_codes=codes,
                  errores=[b.get("error", {}).get("message") for _, b in minted])
        return

    barrier = asyncio.Event()
    ready = 0

    async def synth(k: int, s: dict) -> dict:
        nonlocal ready
        r: dict[str, Any] = {"k": k, "ok": False}
        try:
            async with websockets.connect(s["connect"]["url"], max_size=None, open_timeout=15) as ws:
                ready += 1
                if ready == len(sessions):
                    barrier.set()
                await asyncio.wait_for(barrier.wait(), 20)
                t0 = time.perf_counter()
                await ws.send(json.dumps({
                    "model_id": s["model"], "transcript": SENTENCE, "context_id": f"ctx-{k}-{uuid.uuid4().hex[:6]}",
                    "voice": {"mode": "id", "id": s["config"]["voice_id"]}, "language": s["config"].get("language", "es"),
                    "output_format": {"container": "raw", "encoding": "pcm_s16le", "sample_rate": 24000},
                    "continue": False}))
                audio = 0
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
                    t = msg.get("type")
                    if t == "chunk":
                        if audio == 0:
                            r["ttfa_ms"] = round((time.perf_counter() - t0) * 1000)
                        audio += len(base64.b64decode(msg.get("data") or ""))
                    elif t == "done":
                        r["ok"] = audio > 0
                        break
                    elif t == "error" or msg.get("error"):
                        r["error"] = {k2: msg.get(k2) for k2 in ("status_code", "error", "title", "message") if msg.get(k2)}
                        break
                r["audio_s"] = round(audio / 2 / 24000, 2)
                r["total_ms"] = round((time.perf_counter() - t0) * 1000)
        except Exception as exc:  # noqa: BLE001
            ready += 0
            barrier.set()
            r["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return r
    results = await asyncio.gather(*(synth(k, s) for k, s in enumerate(sessions)))
    okc = sum(r["ok"] for r in results)
    rep.check(f"4 Cartesia {n} síntesis simultáneas con voz clonada", okc == len(sessions),
              mint_codes=codes, tokens_distintos=len(toks), mint_s=round(mint_s, 2), sintetizadas=okc,
              detalle=results)


# ---------------------------------------------------------------------------

async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8200")
    ap.add_argument("--users", type=int, default=8)
    ap.add_argument("--engines", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--cartesia", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--cartesia-n", type=int, default=4)
    ap.add_argument("--isolation", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--rate-limits", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--ip-exhaust", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--json-out", default="")
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    rep = Report()
    print(f"base={base} users={a.users} engines={a.engines} cartesia={a.cartesia} ip_exhaust={a.ip_exhaust}")
    if a.isolation:
        await check_isolation(base, a.users, rep)
    if a.rate_limits:
        await check_rate_limits(base, a.users, rep, a.ip_exhaust)
    if a.engines:
        await check_engines(base, rep)
    if a.cartesia:
        await check_cartesia(base, rep, a.cartesia_n)
    if rep.issues:
        print("\nHallazgos:")
        for i in rep.issues:
            print(" -", i)
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump({"checks": rep.checks, "issues": rep.issues,
                       "samples": [s.__dict__ for s in rep.samples]}, fh, ensure_ascii=False, indent=1, default=str)
    failed = [k for k, v in rep.checks.items() if v["result"] == "FAIL"]
    print(f"\n{len(rep.checks) - len(failed)}/{len(rep.checks)} PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(asyncio.run(main()))
