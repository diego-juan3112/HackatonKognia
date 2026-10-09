/**
 * The console store folds contract events into UI state (docs/08 §2, §6–§9).
 * Synthetic events only: nothing here depends on an engine.
 */
import { beforeEach, describe, expect, it } from "vitest";
import * as store from "../../src/voice/store";
import type { AnyEngineEvent, EngineEvents } from "../../src/voice/types";

const CONV = "conv-store";
let seq = 0;

function ev<K extends keyof EngineEvents>(
  type: K,
  payload: EngineEvents[K],
  over: Partial<Omit<AnyEngineEvent, "type" | "payload">> = {},
): AnyEngineEvent {
  return {
    schema_version: "1",
    event_id: crypto.randomUUID(),
    seq: ++seq,
    conversation_id: CONV,
    turn_id: "turn-1",
    state_version: 1,
    generation_id: null,
    t: seq * 100,
    type,
    payload,
    ...over,
  } as AnyEngineEvent;
}

const user = (text: string, final: boolean, id = "u1", extra: Partial<EngineEvents["transcript"]> = {}): EngineEvents["transcript"] => ({
  role: "user",
  utterance_id: id,
  text,
  final,
  t_start: 100,
  t_end: 400,
  t_source: "engine",
  ...extra,
});

const agent = (text: string, final: boolean, id = "a1"): EngineEvents["transcript"] => ({
  role: "agent",
  utterance_id: id,
  text,
  final,
  t_start: 500,
  t_end: 900,
  t_source: "engine",
});

const trace = { soql: "SELECT 1", ms: 500, rows: 1, cache_status: "live" as const };

beforeEach(() => {
  seq = 0;
  store.reset();
  store.beginSession(CONV, "openai", "modelo-x", true);
});

describe("sesión", () => {
  it("beginSession deja el estado limpio y en marcha", () => {
    const s = store.getState();
    expect(s).toMatchObject({ running: true, conversation_id: CONV, engine: "openai", model: "modelo-x", simulated: true });
    expect(s.utterances).toEqual([]);
    expect(s.tools).toEqual([]);
  });

  it("descarta eventos de otra conversación (A-17)", () => {
    store.dispatch(ev("transcript", user("hola", true), { conversation_id: "otra-sesion" }));
    store.dispatch(ev("status", { state: "speaking" }, { conversation_id: "otra-sesion" }));
    expect(store.getState().utterances).toEqual([]);
    expect(store.getState().status).toBe("idle");
  });

  it("state_version solo sube", () => {
    store.dispatch(ev("status", { state: "listening" }, { state_version: 3 }));
    store.dispatch(ev("status", { state: "thinking" }, { state_version: 2 }));
    expect(store.getState().state_version).toBe(3);
  });

  it("Reiniciar borra conversación, consultas, afecto, avisos y el consentimiento de voz (A-25)", () => {
    store.setVoiceAnalysis(true);
    store.dispatch(ev("transcript", user("hola", true)));
    store.dispatch(ev("tool_call", { tool_call_id: "c1", name: "aggregate_ips", args: {} }));
    store.dispatch(ev("error", { code: "ENGINE_DROPPED", message: "x", retryable: true }));
    store.setEngine("gemini", "g", true);
    store.reset();
    const s = store.getState();
    expect(s).toMatchObject({ running: false, status: "idle", conversation_id: null, voiceAnalysis: false, lastError: null });
    expect([s.utterances, s.tools, s.affect, s.turns, s.notices]).toEqual([[], [], [], [], []]);
    expect(s.evidence).toEqual({});
    expect(s.engine).toBe("gemini"); // the engine is a setting, not conversation state
  });
});

describe("transcripción", () => {
  it("parcial → final se funden en un solo enunciado por utterance_id", () => {
    store.dispatch(ev("transcript", user("¿Cuántas", false)));
    store.dispatch(ev("transcript", user("¿Cuántas camas", false)));
    expect(store.getState().utterances).toHaveLength(1);
    expect(store.getState().utterances[0]).toMatchObject({ text: "¿Cuántas camas", final: false });
    store.dispatch(ev("transcript", user("¿Cuántas camas hay?", true, "u1", { t_end: 900 })));
    const [u] = store.getState().utterances;
    expect(store.getState().utterances).toHaveLength(1);
    expect(u).toMatchObject({ id: "u1", role: "user", text: "¿Cuántas camas hay?", final: true, t_start: 100, t_end: 900, turn_id: "turn-1" });
  });

  it("el final del usuario abre el turno en las métricas", () => {
    store.dispatch(ev("transcript", user("¿Cuántas camas hay?", true)));
    expect(store.getState().turns).toHaveLength(1);
    expect(store.getState().turns[0]).toMatchObject({ turn_id: "turn-1", n: 1, question: "¿Cuántas camas hay?", engine: "openai" });
  });

  it("una corrección conserva el original y guarda el texto corregido (A-09)", () => {
    store.dispatch(ev("transcript", user("¿Cuántas camas hay en Medellín?", true)));
    store.dispatch(ev("transcript", user("¿Cuántas camas hay en Melgar?", true, "u2", { corrects: "u1" }), { turn_id: "turn-2" }));
    const s = store.getState();
    expect(s.utterances).toHaveLength(1);
    expect(s.utterances[0]!.text).toBe("¿Cuántas camas hay en Medellín?");
    expect(s.utterances[0]!.correction?.text).toBe("¿Cuántas camas hay en Melgar?");
    expect(s.utterances[0]!.correction?.reason).toBeTruthy();
  });

  it("el agente toma el tipo de habla en curso (ack, answer, brief)", () => {
    store.dispatch(ev("speech", { phase: "start", generation_id: "g1", kind: "ack" }, { generation_id: "g1" }));
    store.dispatch(ev("transcript", agent("Déjame verificarlo.", true), { generation_id: "g1" }));
    expect(store.getState().utterances[0]).toMatchObject({ kind: "ack", generation_id: "g1" });
  });
});

describe("interrupción (docs/08 §6)", () => {
  const speak = (): void => {
    store.dispatch(ev("transcript", user("¿Cuántas camas hay en Medellín?", true)));
    store.dispatch(ev("speech", { phase: "start", generation_id: "g1", kind: "answer" }, { generation_id: "g1" }));
    store.dispatch(ev("transcript", agent("En Medellín hay 6.280 camas instaladas, según el REPS", false), { generation_id: "g1" }));
  };

  it("guarda solo lo escuchado y conserva el resto como texto no oído", () => {
    speak();
    store.dispatch(ev("interrupted", { generation_id: "g1", played_ms: 800, delivered_text: "En Medellín hay" }, { generation_id: "g1" }));
    const a = store.getState().utterances.find((u) => u.role === "agent")!;
    expect(a.delivered_text).toBe("En Medellín hay");
    expect(a.text.startsWith(a.delivered_text!)).toBe(true);
    expect(a.text.length).toBeGreaterThan(a.delivered_text!.length);
    expect(store.getState().turns[0]!.interrupted_at).not.toBeNull();
  });

  it("descarta el texto tardío de una generación ya interrumpida (docs/08 §6.5, §13)", () => {
    speak();
    store.dispatch(ev("interrupted", { generation_id: "g1", played_ms: 800, delivered_text: "En Medellín hay" }, { generation_id: "g1" }));
    const before = store.getState().utterances.find((u) => u.role === "agent")!.text;
    // The provider kept generating: this chunk arrives after the cut.
    store.dispatch(ev("transcript", agent(`${before}, con corte a noviembre de 2022. Es capacidad instalada.`, false), { generation_id: "g1" }));
    expect(store.getState().utterances.find((u) => u.role === "agent")!.text).toBe(before);
  });

  it("calcula la parada de reproducción desde la interrupción", () => {
    speak();
    const cut = ev("interrupted", { generation_id: "g1", played_ms: 800, delivered_text: "En Medellín hay" }, { generation_id: "g1" });
    store.dispatch(cut);
    store.dispatch(ev("latency", { t_speech_end: 400, t_first_useful_audio: 1400, t_playback_stop: cut.t + 90 }));
    expect(store.getState().turns[0]).toMatchObject({ first_useful_ms: 1000, stop_ms: 90 });
  });
});

describe("herramientas y evidencia (docs/08 §5)", () => {
  it("tool_call + tool_result quedan en una sola entrada con su traza", () => {
    store.dispatch(ev("transcript", user("¿Cuántas camas hay?", true)));
    store.dispatch(ev("tool_call", { tool_call_id: "c1", name: "aggregate_ips", args: { metric: "capacity_sum" } }));
    expect(store.getState().tools[0]).toMatchObject({ tool_call_id: "c1", invalidated: false });
    expect(store.getState().tools[0]!.status).toBeUndefined();
    store.dispatch(ev("tool_result", { tool_call_id: "c1", status: "ok", trace, evidence_ref: "sha256:x" }));
    expect(store.getState().tools).toHaveLength(1);
    expect(store.getState().tools[0]).toMatchObject({ status: "ok", trace, evidence_ref: "sha256:x", turn_id: "turn-1" });
    expect(store.getState().turns[0]).toMatchObject({ rows: 1, cache: "live" });
  });

  it("un tool_result sin tool_call previo se ignora", () => {
    store.dispatch(ev("tool_result", { tool_call_id: "fantasma", status: "ok", trace, evidence_ref: "sha256:x" }));
    expect(store.getState().tools).toEqual([]);
  });

  it("un evento reenviado (mismo event_id) no duplica la consulta (A-17)", () => {
    const call = ev("tool_call", { tool_call_id: "c1", name: "aggregate_ips", args: {} });
    store.dispatch(call);
    store.dispatch(call);
    expect(store.getState().tools).toHaveLength(1);
  });

  it("una corrección exitosa invalida la evidencia del turno corregido y solo esa (A-09)", () => {
    store.dispatch(ev("tool_call", { tool_call_id: "c1", name: "aggregate_ips", args: {} }, { turn_id: "turn-1" }));
    store.dispatch(ev("tool_result", { tool_call_id: "c1", status: "ok", trace, evidence_ref: "sha256:a" }, { turn_id: "turn-1" }));
    store.dispatch(ev("tool_call", { tool_call_id: "c0", name: "aggregate_ips", args: {} }, { turn_id: "turn-0" }));
    store.dispatch(ev("tool_call", { tool_call_id: "c2", name: "correct_context", args: { target_turn_id: "turn-1" } }, { turn_id: "turn-2" }));
    expect(store.getState().tools.find((t) => t.tool_call_id === "c1")!.invalidated).toBe(false);
    store.dispatch(ev("tool_result", { tool_call_id: "c2", status: "ok", trace, evidence_ref: "sha256:b" }, { turn_id: "turn-2", state_version: 2 }));
    const byId = Object.fromEntries(store.getState().tools.map((t) => [t.tool_call_id, t.invalidated]));
    expect(byId).toEqual({ c1: true, c0: false, c2: false });
    expect(store.getState().state_version).toBe(2);
  });

  it("una corrección fallida no invalida nada", () => {
    store.dispatch(ev("tool_call", { tool_call_id: "c1", name: "aggregate_ips", args: {} }));
    store.dispatch(ev("tool_call", { tool_call_id: "c2", name: "correct_context", args: { target_turn_id: "turn-1" } }, { turn_id: "turn-2" }));
    store.dispatch(ev("tool_result", { tool_call_id: "c2", status: "unavailable", trace, evidence_ref: "x" }, { turn_id: "turn-2" }));
    expect(store.getState().tools[0]!.invalidated).toBe(false);
  });
});

describe("sesión renovada y cambio de motor (docs/08 §7, A-23)", () => {
  it("`switched` cambia el motor activo, cuenta el intento y avisa «sesión renovada»", () => {
    store.dispatch(ev("transcript", user("¿Cuántas camas hay?", true)));
    store.dispatch(ev("session", { event: "switched", from: "openai", to: "gemini", reason: "ENGINE_DROPPED", attempt: 1 }));
    const s = store.getState();
    expect(s.engine).toBe("gemini");
    expect(s.turns[0]!.attempts).toBe(2);
    expect(s.notices).toHaveLength(1);
    expect(s.notices[0]!.kind).toBe("session");
    expect(s.notices[0]!.text).toMatch(/Sesión renovada/);
    expect(s.notices[0]!.text).toMatch(/Gemini Live/);
  });

  it("`renewed` avisa sin cambiar de motor", () => {
    store.dispatch(ev("session", { event: "renewed", reason: "socket cerrado", attempt: 1 }));
    expect(store.getState().engine).toBe("openai");
    expect(store.getState().notices[0]!.text).toMatch(/Sesión renovada con el mismo motor/);
  });

  it("`expiring` avisa y no cuenta como intento", () => {
    store.dispatch(ev("transcript", user("hola", true)));
    store.dispatch(ev("session", { event: "expiring", reason: "goAway", attempt: 0 }));
    expect(store.getState().turns[0]!.attempts).toBe(1);
    expect(store.getState().notices[0]!.text).toMatch(/por vencer/);
  });

  it("un error queda como último error y como aviso", () => {
    store.dispatch(ev("error", { code: "ENGINE_DROPPED", message: "El motor cerró la conexión.", retryable: true }));
    expect(store.getState().lastError?.code).toBe("ENGINE_DROPPED");
    expect(store.getState().notices[0]).toMatchObject({ kind: "error", text: "El motor cerró la conexión." });
  });
});

describe("latencia (docs/08 §9)", () => {
  it("desglosa aviso previo, herramienta y primer audio útil respecto del fin de la voz", () => {
    store.dispatch(ev("transcript", user("¿Cuántas camas hay?", true)));
    store.dispatch(ev("latency", { t_speech_end: 1000, t_ack_audio: 1260, t_tool_start: 1900, t_tool_end: 2400, t_first_useful_audio: 2580 }));
    expect(store.getState().turns[0]).toMatchObject({ ack_ms: 260, tool_start_ms: 900, tool_ms: 500, first_useful_ms: 1580, stop_ms: null });
  });
});
