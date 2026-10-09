"""Latency bench WITH a data query for both voice engines (R-29, docs/07 section 8).

It walks the same path as the browser:

    POST /sessions -> POST /realtime/session -> provider WebSocket (audio in real time)
    -> function call -> POST /tools/{name} -> function output -> first useful audio

so whatever session config the backend sets (model, VAD, instructions, tools) is
what gets measured. Each question is synthesized once with OpenAI TTS
(gpt-4o-mini-tts, voice ash, PCM16 24 kHz) and cached OUTSIDE the repo; it is
streamed in 20 ms chunks at wall-clock pace and followed by silence (an open
microphone keeps sending silence until the turn ends).

All times are monotonic ms relative to t0 = the moment the last voiced 20 ms
chunk of the question was sent (end of the user's speech):

    a  speech end seen by the provider (OpenAI ``input_audio_buffer.speech_stopped``;
       Gemini has no such event: first server message received after t0)
    b  tool decision (OpenAI ``response.function_call_arguments.done``; Gemini ``toolCall``)
    c  tool: POST /tools round-trip ms, and the envelope's ``trace.ms``
    d  first useful audio = first audio delta after the last tool result was sent;
       ack = first audio delta before the tool call ("muletilla") and its duration

Usage (from the repo root, so pydantic-settings finds .env):

    python scripts/bench_models.py --engine both --n 10 --label before --serve
    python scripts/bench_models.py --engine openai --label after-gpt-realtime --serve \
        --env VOICE_OPENAI_MODEL=gpt-realtime

``--serve`` starts ``uvicorn api.app_voice:app`` locally with the given env
overrides; without it ``--base-url`` must point at a running server.
Failures are reported verbatim, never dropped (R-29). No secret is printed (R-05).
"""

from __future__ import annotations

import argparse
import array
import asyncio
import base64
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from websockets.asyncio.client import connect as ws_connect

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

AUDIO_DIR = Path(os.environ.get("BENCH_AUDIO_DIR", r"C:\dev\kognia\bench-audio"))
QUESTIONS = ROOT / "tests" / "fixtures" / "bench_questions.yaml"
RESULTS = ROOT / "docs" / "anexos" / "bench-latencia-2026-10-09.md"
CHUNK_MS = 20
MIN_TRAIL_SILENCE_MS = 1500
VOICED_RMS = 300.0
TURN_TIMEOUT_S = 30.0
TTS_MODEL, TTS_VOICE = "gpt-4o-mini-tts", "ash"


def now() -> float:
    return time.perf_counter()


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


async def tts_pcm24(text: str, key: str) -> bytes:
    """OpenAI TTS -> raw PCM16 mono 24 kHz, cached by (model, voice, text)."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{TTS_MODEL}|{TTS_VOICE}|{text}".encode()).hexdigest()[:16]
    path = AUDIO_DIR / f"{digest}.pcm24"
    if path.exists():
        return path.read_bytes()
    if not key:
        raise RuntimeError("OPENAI_API_KEY vacío: no se puede sintetizar la pregunta")
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.openai.com/v1/audio/speech",
                         headers={"Authorization": f"Bearer {key}"},
                         json={"model": TTS_MODEL, "voice": TTS_VOICE, "input": text, "response_format": "pcm",
                               "instructions": "Habla en español de Colombia, como una persona que pregunta "
                                               "con naturalidad, sin pausas largas."})
    if r.status_code != 200:
        raise RuntimeError(f"TTS HTTP {r.status_code}: {r.text[:200]}")
    path.write_bytes(r.content)
    return r.content


def resample_24_to_16(pcm: bytes) -> bytes:
    src = array.array("h")
    src.frombytes(pcm[: len(pcm) // 2 * 2])
    n_out = len(src) * 2 // 3
    out = array.array("h", [0]) * n_out
    last = len(src) - 1
    for i in range(n_out):
        pos = i * 1.5
        j = int(pos)
        frac = pos - j
        a = src[j]
        b = src[j + 1] if j < last else a
        out[i] = int(a + (b - a) * frac)
    return out.tobytes()


def split_chunks(pcm: bytes, rate: int) -> list[bytes]:
    size = rate * CHUNK_MS // 1000 * 2
    return [pcm[i:i + size] for i in range(0, len(pcm), size)]


def rms(chunk: bytes) -> float:
    a = array.array("h")
    a.frombytes(chunk[: len(chunk) // 2 * 2])
    return math.sqrt(sum(x * x for x in a) / len(a)) if a else 0.0


async def stream_mic(send, pcm: bytes, rate: int, rec: Turn, stop: asyncio.Event, start_at: float = 0.0) -> None:
    """Send like a microphone: chunk k leaves when it has been 'captured' (start + (k+1)*20 ms)."""
    if start_at > now():
        await asyncio.sleep(start_at - now())  # the person starts talking a moment after connecting
    chunks = split_chunks(pcm, rate)
    voiced = [i for i, c in enumerate(chunks) if rms(c) >= VOICED_RMS]
    last_voiced = voiced[-1] if voiced else len(chunks) - 1
    rec.speech_ms = (last_voiced + 1) * CHUNK_MS
    silence = bytes(rate * CHUNK_MS // 1000 * 2)
    start = now()
    k = 0

    async def pace() -> None:
        delay = start + (k + 1) * CHUNK_MS / 1000 - now()
        if delay > 0:
            await asyncio.sleep(delay)

    for i, c in enumerate(chunks):
        await pace()
        await send(c)
        k += 1
        if i == last_voiced:
            rec.t0 = now()
    trail_until = now() + MIN_TRAIL_SILENCE_MS / 1000
    while not stop.is_set() or now() < trail_until:
        if stop.is_set() and now() >= trail_until:
            break
        await pace()
        await send(silence)
        k += 1


# ---------------------------------------------------------------------------
# One turn record
# ---------------------------------------------------------------------------


@dataclass
class Turn:
    qid: str
    text: str
    engine: str
    model: str = ""
    t0: float | None = None
    speech_ms: int = 0
    cred_ms: int | None = None
    connect_ms: int | None = None
    a: float | None = None          # absolute perf_counter times; converted on export
    a_kind: str = ""
    b: float | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_sent: list[float] = field(default_factory=list)
    audio: list[tuple[float, int, str]] = field(default_factory=list)  # (t, bytes, segment key)
    ack_segments: set[str] = field(default_factory=set)
    useful_segments: set[str] = field(default_factory=set)
    transcript_in: str = ""
    transcript_out: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    done: float | None = None
    vad: dict[str, Any] | None = None
    vad_audio_end_ms: int | None = None  # OpenAI speech_stopped.audio_end_ms (stream position)

    def rel(self, t: float | None) -> int | None:
        return None if t is None or self.t0 is None else int(round((t - self.t0) * 1000))

    def export(self) -> dict[str, Any]:
        ack = [x for x in self.audio if x[2] in self.ack_segments]
        useful = [x for x in self.audio if x[2] in self.useful_segments]
        unavailable = sum(1 for t in self.tools if t.get("status") == "unavailable")
        failures = list(self.errors)
        if not self.tools:
            failures.append("no_tool: el modelo respondió sin llamar herramienta")
        for t in self.tools:
            if t.get("status") == "unavailable":
                failures.append(f"tool {t['name']} status=unavailable error={t.get('error')} "
                                f"(POST /tools {t['rt_ms']} ms; args {json.dumps(t['args'], ensure_ascii=False)})")
        if self.tools and not useful:
            failures.append("no_useful_audio: no llegó audio después del resultado de la herramienta")
        if self.t0 is None:
            failures.append("no_t0: no se detectó voz en el audio de la pregunta")
        return {
            "qid": self.qid, "text": self.text, "engine": self.engine, "model": self.model,
            "speech_ms": self.speech_ms, "cred_ms": self.cred_ms, "connect_ms": self.connect_ms,
            "a_speech_end": self.rel(self.a), "a_kind": self.a_kind,
            "b_tool_decision": self.rel(self.b),
            "c_tool_rt_ms": sum(t["rt_ms"] for t in self.tools) if self.tools else None,
            "c_trace_ms": sum(t.get("trace_ms") or 0 for t in self.tools) if self.tools else None,
            "d_first_useful": self.rel(useful[0][0]) if useful else None,
            "ack_first": self.rel(ack[0][0]) if ack else None,
            "ack_audio_ms": int(sum(x[1] for x in ack) / 48) if ack else 0,
            "useful_audio_ms": int(sum(x[1] for x in useful) / 48) if useful else 0,
            "turn_done": self.rel(self.done),
            # Audible = when the useful audio can actually be heard if the ack plays to the end.
            "d_audible": (max(self.rel(useful[0][0]), self.rel(ack[0][0]) + int(sum(x[1] for x in ack) / 48))
                          if useful and ack else (self.rel(useful[0][0]) if useful else None)),
            "vad_audio_end_ms": self.vad_audio_end_ms,
            "tool_rounds": len(self.tool_sent),
            "tools": [{k: v for k, v in t.items() if k != "output"} for t in self.tools],
            "unavailable": unavailable,
            "transcript_in": self.transcript_in.strip(),
            "transcript_out": [s.strip() for s in self.transcript_out if s.strip()],
            "failures": failures,
            "vad": self.vad,
        }


def redact(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "<redactado>")
    return text


# ---------------------------------------------------------------------------
# Backend calls (the same ones the web client makes)
# ---------------------------------------------------------------------------


async def new_session(http: httpx.AsyncClient, base: str) -> str:
    r = await http.post(f"{base}/sessions", json={})
    r.raise_for_status()
    return r.json()["token"]


async def mint(http: httpx.AsyncClient, base: str, tok: str, engine: str) -> dict[str, Any]:
    r = await http.post(f"{base}/realtime/session", headers={"X-Session-Token": tok},
                        json={"engine": engine, "conversation_id": f"bench-{uuid.uuid4().hex[:12]}"})
    if r.status_code != 200:
        raise RuntimeError(f"/realtime/session HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


async def run_tool(http: httpx.AsyncClient, base: str, tok: str, name: str, call_id: str,
                   args: dict[str, Any], force_live: bool) -> dict[str, Any]:
    t = now()
    try:
        r = await http.post(f"{base}/tools/{name}", headers={"X-Session-Token": tok}, timeout=15,
                            json={"tool_call_id": call_id[:128], "args": args, "force_live": force_live})
        rt = int((now() - t) * 1000)
        if r.status_code == 200:
            env = r.json()
            trace = env.get("trace") or {}
            output = {"status": env.get("status"), "for_model": env.get("for_model", ""),
                      "data": env.get("data", {}), "warnings": (env.get("evidence") or {}).get("warnings", [])}
            return {"name": name, "args": args, "http": 200, "rt_ms": rt, "trace_ms": trace.get("ms"),
                    "cache_status": trace.get("cache_status"), "status": env.get("status"),
                    "error": (env.get("error") or {}).get("code") if env.get("error") else None, "output": output}
        body = r.text[:200]
    except httpx.HTTPError as exc:
        rt, r, body = int((now() - t) * 1000), None, f"{type(exc).__name__}"
    output = {"status": "unavailable", "for_model": "La consulta a datos.gov.co no respondió; no inventes cifras.",
              "data": {}, "warnings": []}
    return {"name": name, "args": args, "http": r.status_code if r is not None else None, "rt_ms": rt,
            "trace_ms": None, "cache_status": None, "status": "unavailable", "error": body, "output": output}


# ---------------------------------------------------------------------------
# OpenAI Realtime
# ---------------------------------------------------------------------------


async def turn_openai(http: httpx.AsyncClient, base: str, q: dict, pcm24: bytes, force_live: bool,
                      pre_wait: float = 0.0) -> Turn:
    rec = Turn(q["id"], q["text"], "openai")
    tok = await new_session(http, base)
    t = now()
    rs = await mint(http, base, tok, "openai")
    rec.cred_ms = int((now() - t) * 1000)
    minted = now()
    rec.model = rs.get("model", "")
    rec.vad = (rs.get("config") or {}).get("turn_detection")
    secrets = [rs["connect"].get("token") or ""]
    t = now()
    async with ws_connect(rs["connect"]["url"], subprotocols=rs["connect"]["protocols"],
                          max_size=None, open_timeout=10) as ws:
        rec.connect_ms = int((now() - t) * 1000)
        stop = asyncio.Event()
        resp_has_call: dict[str, bool] = {}
        resp_post: dict[str, bool] = {}
        state = {"active": None, "outstanding": 0, "pending_create": False, "post": False,
                 "first_tool_done": False}

        async def send_audio(c: bytes) -> None:
            await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(c).decode()}))

        async def do_tool(name: str, call_id: str, raw_args: str) -> None:
            try:
                args = json.loads(raw_args or "{}")
            except json.JSONDecodeError:
                args = {}
                rec.errors.append(f"argumentos no JSON en {name}: {raw_args[:120]}")
            fl = force_live and not state["first_tool_done"]
            state["first_tool_done"] = True
            res = await run_tool(http, base, tok, name, call_id, args, fl)
            rec.tools.append(res)
            await ws.send(json.dumps({"type": "conversation.item.create", "item": {
                "type": "function_call_output", "call_id": call_id,
                "output": json.dumps(res["output"], ensure_ascii=False)}}))
            state["outstanding"] -= 1
            if state["outstanding"] == 0:
                if state["active"] is None:
                    await create_response()
                else:
                    state["pending_create"] = True

        async def create_response() -> None:
            state["pending_create"] = False
            state["post"] = True
            rec.tool_sent.append(now())
            await ws.send(json.dumps({"type": "response.create"}))

        mic: asyncio.Task | None = None
        deadline = now() + TURN_TIMEOUT_S + 15
        tasks: list[asyncio.Task] = []
        try:
            while True:
                remaining = deadline - now()
                if remaining <= 0:
                    rec.errors.append("timeout: el turno no terminó en 45 s")
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), remaining)
                except TimeoutError:
                    rec.errors.append("timeout: el turno no terminó en 45 s")
                    break
                ev = json.loads(raw)
                et = ev.get("type", "")
                tnow = now()
                if et == "session.created" and mic is None:
                    mic = asyncio.create_task(stream_mic(send_audio, pcm24, 24000, rec, stop, minted + pre_wait))
                elif et == "input_audio_buffer.speech_stopped" and rec.a is None:
                    rec.a, rec.a_kind = tnow, "speech_stopped"
                    rec.vad_audio_end_ms = ev.get("audio_end_ms")
                elif et == "conversation.item.input_audio_transcription.completed":
                    rec.transcript_in += ev.get("transcript", "")
                elif et == "response.created":
                    rid = ev["response"]["id"]
                    state["active"] = rid
                    resp_post[rid] = state["post"]
                elif et in ("response.output_audio.delta", "response.audio.delta"):
                    rec.audio.append((tnow, len(base64.b64decode(ev.get("delta", ""))), ev.get("response_id", "")))
                elif et in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
                    tag = "post" if resp_post.get(ev.get("response_id", "")) else "pre"
                    rec.transcript_out.append(f"[{tag}] {ev.get('transcript', '')}")
                elif et == "response.output_item.added" and (ev.get("item") or {}).get("type") == "function_call":
                    resp_has_call[ev.get("response_id", "")] = True
                elif et == "response.function_call_arguments.done":
                    if rec.b is None:
                        rec.b = tnow
                    resp_has_call[ev.get("response_id", "")] = True
                    state["outstanding"] += 1
                    tasks.append(asyncio.create_task(do_tool(ev.get("name", ""), ev.get("call_id", ""),
                                                             ev.get("arguments", ""))))
                elif et == "response.done":
                    resp = ev.get("response") or {}
                    rid = resp.get("id", "")
                    if any(o.get("type") == "function_call" for o in resp.get("output") or []):
                        resp_has_call[rid] = True
                    if resp.get("status") not in ("completed", None):
                        rec.errors.append(f"response.done status={resp.get('status')} "
                                          f"{json.dumps(resp.get('status_details'), ensure_ascii=False)[:300]}")
                    state["active"] = None
                    if state["pending_create"] and state["outstanding"] == 0:
                        await create_response()
                    elif not resp_has_call.get(rid) and state["outstanding"] == 0 and not state["pending_create"]:
                        if resp_post.get(rid) or not rec.tools:
                            rec.done = tnow
                            break
                elif et == "error":
                    err = ev.get("error") or {}
                    rec.errors.append(redact(f"error {err.get('code')}: {err.get('message')}", secrets))
        except Exception as exc:  # noqa: BLE001 - report verbatim (R-29)
            rec.errors.append(redact(f"{type(exc).__name__}: {exc}", secrets))
        finally:
            stop.set()
            for tk in tasks:
                if not tk.done():
                    tk.cancel()
            if mic is not None:
                mic.cancel()
                try:
                    await mic
                except (asyncio.CancelledError, Exception):
                    pass
        # classify audio segments by response id
        for rid, post in resp_post.items():
            if not post:
                rec.ack_segments.add(rid)
            elif not resp_has_call.get(rid):
                rec.useful_segments.add(rid)
    return rec


# ---------------------------------------------------------------------------
# Gemini Live
# ---------------------------------------------------------------------------


async def turn_gemini(http: httpx.AsyncClient, base: str, q: dict, pcm16: bytes, force_live: bool,
                      pre_wait: float = 0.0) -> Turn:
    rec = Turn(q["id"], q["text"], "gemini")
    tok = await new_session(http, base)
    t = now()
    rs = await mint(http, base, tok, "gemini")
    rec.cred_ms = int((now() - t) * 1000)
    minted = now()
    rec.model = rs.get("model", "")
    rec.vad = (rs.get("config") or {}).get("turn_detection")
    secrets = [rs["connect"].get("token") or ""]
    setup = (rs.get("config") or {}).get("setup") or {"model": f"models/{rec.model}"}
    t = now()
    async with ws_connect(rs["connect"]["url"], max_size=None, open_timeout=10) as ws:
        rec.connect_ms = int((now() - t) * 1000)
        await ws.send(json.dumps({"setup": setup}))
        stop = asyncio.Event()
        state = {"seg": 0, "outstanding": 0, "first_tool_done": False}
        seg_has_call: dict[str, bool] = {}

        async def send_audio(c: bytes) -> None:
            await ws.send(json.dumps({"realtimeInput": {"audio": {"data": base64.b64encode(c).decode(),
                                                                   "mimeType": "audio/pcm;rate=16000"}}}))

        async def do_tools(calls: list[dict]) -> None:
            responses = []
            results = []
            for fc in calls:
                fl = force_live and not state["first_tool_done"]
                state["first_tool_done"] = True
                results.append(run_tool(http, base, tok, fc.get("name", ""), fc.get("id") or uuid.uuid4().hex,
                                        fc.get("args") or {}, fl))
            for fc, res in zip(calls, await asyncio.gather(*results)):
                rec.tools.append(res)
                responses.append({"id": fc.get("id"), "name": fc.get("name"), "response": res["output"]})
            await ws.send(json.dumps({"toolResponse": {"functionResponses": responses}}, ensure_ascii=False))
            rec.tool_sent.append(now())
            state["seg"] += 1
            state["outstanding"] -= 1

        mic: asyncio.Task | None = None
        deadline = now() + TURN_TIMEOUT_S + 15
        tasks: list[asyncio.Task] = []
        try:
            while True:
                remaining = deadline - now()
                if remaining <= 0:
                    rec.errors.append("timeout: el turno no terminó en 45 s")
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), remaining)
                except TimeoutError:
                    rec.errors.append("timeout: el turno no terminó en 45 s")
                    break
                msg = json.loads(raw)
                tnow = now()
                kinds = [k for k in msg if k != "usageMetadata"] or ["usageMetadata"]
                if rec.t0 is not None and rec.a is None and tnow > rec.t0:
                    sc = msg.get("serverContent") or {}
                    sub = [k for k in sc] if sc else []
                    rec.a, rec.a_kind = tnow, "first_msg:" + "+".join(kinds + sub)
                if "setupComplete" in msg and mic is None:
                    mic = asyncio.create_task(stream_mic(send_audio, pcm16, 16000, rec, stop, minted + pre_wait))
                if "toolCall" in msg:
                    if rec.b is None:
                        rec.b = tnow
                    seg_has_call[str(state["seg"])] = True
                    state["outstanding"] += 1
                    tasks.append(asyncio.create_task(do_tools(msg["toolCall"].get("functionCalls") or [])))
                if "toolCallCancellation" in msg:
                    rec.errors.append(f"toolCallCancellation {json.dumps(msg['toolCallCancellation'])[:200]}")
                if "goAway" in msg:
                    rec.errors.append(f"goAway {json.dumps(msg['goAway'])[:200]}")
                sc = msg.get("serverContent") or {}
                if sc.get("inputTranscription"):
                    rec.transcript_in += sc["inputTranscription"].get("text", "")
                if sc.get("outputTranscription"):
                    tag = "post" if state["seg"] > 0 else "pre"
                    txt = sc["outputTranscription"].get("text", "")
                    if rec.transcript_out and rec.transcript_out[-1].startswith(f"[{tag}]"):
                        rec.transcript_out[-1] += txt
                    else:
                        rec.transcript_out.append(f"[{tag}] {txt}")
                for part in (sc.get("modelTurn") or {}).get("parts") or []:
                    data = (part.get("inlineData") or {}).get("data")
                    if data:
                        rec.audio.append((tnow, len(base64.b64decode(data)), str(state["seg"])))
                if sc.get("interrupted"):
                    rec.errors.append("interrupted: Gemini marcó el turno como interrumpido")
                if sc.get("turnComplete") and state["outstanding"] == 0:
                    if state["seg"] > 0 or not rec.tools:
                        if state["seg"] > 0 and not any(x[2] == str(state["seg"]) for x in rec.audio):
                            continue  # turnComplete of the pre-tool part; keep waiting
                        rec.done = tnow
                        break
        except Exception as exc:  # noqa: BLE001 - report verbatim (R-29)
            rec.errors.append(redact(f"{type(exc).__name__}: {exc}", secrets))
        finally:
            stop.set()
            for tk in tasks:
                if not tk.done():
                    tk.cancel()
            if mic is not None:
                mic.cancel()
                try:
                    await mic
                except (asyncio.CancelledError, Exception):
                    pass
        rec.ack_segments.add("0")
        last = str(len(rec.tool_sent))
        if rec.tool_sent:
            rec.useful_segments.add(last)
    return rec


# ---------------------------------------------------------------------------
# Server, stats and report
# ---------------------------------------------------------------------------


def start_server(port: int, env_over: dict[str, str], log_path: Path) -> subprocess.Popen:
    env = {**os.environ, **env_over}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 - lives as long as the server
    return subprocess.Popen([sys.executable, "-m", "uvicorn", "api.app_voice:app", "--app-dir", "src",
                             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)


async def wait_health(http: httpx.AsyncClient, base: str, timeout: float = 40) -> dict[str, Any]:
    end = now() + timeout
    last = ""
    while now() < end:
        try:
            r = await http.get(f"{base}/health", timeout=10)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            last = type(exc).__name__
        await asyncio.sleep(0.5)
    raise RuntimeError(f"el servidor no respondió /health: {last}")


def pct(values: list[int | None], p: float) -> int | None:
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    return v[max(0, math.ceil(p * len(v)) - 1)]  # nearest rank: with n=10, p95 = the worst case


def fmt(v: Any) -> str:
    return "—" if v is None else str(v)


METRICS = [("a_speech_end", "(a) fin de voz detectado"), ("b_tool_decision", "(b) decisión de herramienta"),
           ("c_tool_rt_ms", "(c) POST /tools ida y vuelta (ms)"), ("c_trace_ms", "(c) trace.ms de la fuente"),
           ("ack_first", "reconocimiento previo: primer audio"), ("ack_audio_ms", "reconocimiento previo: duración"),
           ("d_first_useful", "**(d) primer audio útil** (llegada)"),
           ("d_audible", "(d') audible si el reconocimiento suena completo"), ("turn_done", "turno completo"),
           ("cred_ms", "emitir credencial (ms)"), ("connect_ms", "abrir WebSocket (ms)")]


def summarize(rows: list[dict[str, Any]]) -> str:
    lines = ["| Métrica (ms desde t0) | p50 | p95 | n |", "|---|---|---|---|"]
    for key, label in METRICS:
        vals = [r[key] for r in rows]
        if key == "ack_audio_ms":
            vals = [r[key] for r in rows if r["ack_first"] is not None]
        n = sum(1 for x in vals if x is not None)
        lines.append(f"| {label} | {fmt(pct(vals, 0.5))} | {fmt(pct(vals, 0.95))} | {n} |")
    return "\n".join(lines)


def by_cache(rows: list[dict[str, Any]]) -> str:
    """(d) split by the cache status of the first tool call (live vs fresh/stale prefetched)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = (r["tools"][0].get("cache_status") or "?") if r["tools"] else "sin herramienta"
        groups.setdefault(key, []).append(r)
    lines = ["| Caché 1.ª consulta | n | (d) p50 | (d) p95 | (d') p50 | (d') p95 | c rt p50 |", "|---|---|---|---|---|---|---|"]
    for key, g in sorted(groups.items()):
        d = [r["d_first_useful"] for r in g]
        da = [r["d_audible"] for r in g]
        c = [r["c_tool_rt_ms"] for r in g]
        lines.append(f"| {key} | {len(g)} | {fmt(pct(d, .5))} | {fmt(pct(d, .95))} | {fmt(pct(da, .5))} | "
                     f"{fmt(pct(da, .95))} | {fmt(pct(c, .5))} |")
    return "\n".join(lines)


def per_turn(rows: list[dict[str, Any]]) -> str:
    out = ["| q | a | b | c rt/trace | ack@ (dur) | d útil | herramientas (status, caché) | escuchó | respondió |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        tools = "; ".join(f"{t['name']}({t['status']},{t.get('cache_status')})" for t in r["tools"]) or "—"
        ack = f"{fmt(r['ack_first'])} ({r['ack_audio_ms']})" if r["ack_first"] is not None else "—"
        said = " ".join(r["transcript_out"])[:160].replace("|", "/").replace("\n", " ")
        heard = r["transcript_in"][:60].replace("|", "/").replace("\n", " ")
        out.append(f"| {r['qid']} | {fmt(r['a_speech_end'])} | {fmt(r['b_tool_decision'])} | "
                   f"{fmt(r['c_tool_rt_ms'])}/{fmt(r['c_trace_ms'])} | {ack} | {fmt(r['d_first_useful'])} | "
                   f"{tools} | {heard} | {said} |")
    return "\n".join(out)


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%h %s"], capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


def report(label: str, engine: str, rows: list[dict[str, Any]], health: dict[str, Any],
           env_over: dict[str, str], force_live: bool, pre_wait: float = 0.0) -> str:
    model = rows[0]["model"] if rows else health.get("engines", {}).get(engine, {}).get("model", "?")
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    unavailable = sum(r["unavailable"] for r in rows)
    failures = [f"- {r['qid']}: {f}" for r in rows for f in r["failures"]]
    a_kind = sorted({r["a_kind"] for r in rows if r["a_kind"]})
    vad = rows[0]["vad"] if rows else None
    parts = [
        f"\n## {label} · {engine} · `{model}` · {ts}\n",
        f"- Commit: `{git_head()}` · prompt `{health.get('instructions_version')}` · "
        f"overrides: `{json.dumps(env_over) if env_over else 'ninguno'}`",
        f"- Turn detection: `{json.dumps(vad, ensure_ascii=False)}`",
        f"- n = {len(rows)} preguntas, una sesión nueva por pregunta; force_live en la 1.ª consulta: {force_live}; "
        f"espera tras /realtime/session antes de hablar: {pre_wait} s",
        f"- (a) medido con: {', '.join(a_kind) or '—'}",
        f"- Herramientas `unavailable`: {unavailable}\n",
        summarize(rows), "",
        by_cache(rows), "",
        "<details><summary>Por turno</summary>\n", per_turn(rows), "\n</details>\n",
        "**Fallos (verbatim, R-29):**", *(failures or ["- ninguno"]), "",
    ]
    return "\n".join(parts)


HEADER = """# Bench de latencia con consulta — 2026-10-09

Generado por `scripts/bench_models.py` (R-29, [07](../07-reto-01-especificacion.md) §8: primer
audio útil con consulta p95 ≤ 4,0 s; reconocimiento previo ≤ 1,0 s, se mide aparte).

**Método.** Cada pregunta se sintetiza una vez con OpenAI TTS (`gpt-4o-mini-tts`, voz `ash`,
PCM16 24 kHz; 16 kHz para Gemini por remuestreo lineal) y se envía por el WebSocket del
proveedor en tramas de 20 ms a ritmo de reloj, seguida de silencio (micrófono abierto) hasta que
termina el turno. Credencial, sesión y herramientas pasan por el backend local
(`POST /sessions`, `POST /realtime/session`, `POST /tools/{name}`), como el navegador. Tiempos en
ms con reloj monótono del cliente desde **t0 = envío del último fragmento con voz**. La salida
de la función es `{status, for_model, data, warnings}`. Sin reproducción de audio ni eco: la
latencia de reproducción del navegador no está incluida. p95 por rango más cercano: con n = 10
es el peor caso. Desde un equipo en Colombia, servidor local (no Vercel).
"""


async def main_async(args: argparse.Namespace) -> int:
    from config import get_settings  # reads .env from cwd (repo root)

    settings = get_settings()
    qs = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    if args.only:
        qs = [q for q in qs if q["id"] in args.only.split(",")]
    qs = qs[: args.n]
    env_over = dict(kv.split("=", 1) for kv in args.env)
    engines = ["openai", "gemini"] if args.engine == "both" else [args.engine]
    base = args.base_url.rstrip("/")
    proc = None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if args.serve:
        port = int(base.rsplit(":", 1)[1])
        proc = start_server(port, env_over, AUDIO_DIR / f"server-{args.label}-{stamp}.log")
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            health = await wait_health(http, base)
            audio24 = {q["id"]: await tts_pcm24(q.get("say") or q["text"], settings.openai_api_key) for q in qs}
            audio16 = {k: resample_24_to_16(v) for k, v in audio24.items()} if "gemini" in engines else {}
            for engine in engines:
                rows = []
                for q in qs:
                    try:
                        if engine == "openai":
                            rec = await turn_openai(http, base, q, audio24[q["id"]], not args.no_force_live,
                                                    args.pre_wait)
                        else:
                            rec = await turn_gemini(http, base, q, audio16[q["id"]], not args.no_force_live,
                                                    args.pre_wait)
                        row = rec.export()
                    except Exception as exc:  # noqa: BLE001 - reported verbatim (R-29)
                        row = Turn(q["id"], q["text"], engine).export()
                        row["failures"].insert(0, f"excepción {type(exc).__name__}: {str(exc)[:300]}")
                    rows.append(row)
                    print(f"[{engine}] {q['id']} a={row['a_speech_end']} b={row['b_tool_decision']} "
                          f"c={row['c_tool_rt_ms']}/{row['c_trace_ms']} ack={row['ack_first']}({row['ack_audio_ms']}) "
                          f"d={row['d_first_useful']} fails={row['failures']}", flush=True)
                    await asyncio.sleep(args.pause)
                md = report(args.label, engine, rows, health, env_over, not args.no_force_live, args.pre_wait)
                print(md, flush=True)
                if not args.no_write:
                    if not RESULTS.exists():
                        RESULTS.write_text(HEADER, encoding="utf-8")
                    with RESULTS.open("a", encoding="utf-8") as f:
                        f.write(md)
                raw = AUDIO_DIR / f"results-{args.label}-{engine}-{stamp}.json"
                raw.write_text(json.dumps({"label": args.label, "engine": engine, "env": env_over,
                                           "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--engine", choices=["openai", "gemini", "both"], default="both")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--only", default="", help="ids separados por coma, p. ej. q01")
    p.add_argument("--label", default="before")
    p.add_argument("--base-url", default="http://127.0.0.1:8765")
    p.add_argument("--serve", action="store_true", help="arranca uvicorn local con --env")
    p.add_argument("--env", action="append", default=[], help="KEY=VAL para el servidor (--serve)")
    p.add_argument("--no-force-live", action="store_true",
                   help="no forzar consulta en vivo en la 1.ª herramienta (el cliente web sí la fuerza)")
    p.add_argument("--no-write", action="store_true", help="no anexar al Markdown de resultados")
    p.add_argument("--pause", type=float, default=1.0)
    p.add_argument("--pre-wait", type=float, default=0.0,
                   help="segundos entre POST /realtime/session y el inicio de la voz (deja terminar la precarga)")
    args = p.parse_args()
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
