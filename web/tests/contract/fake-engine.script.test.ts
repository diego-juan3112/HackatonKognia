/**
 * Contract of the scripted session (docs/08 §2, §5, §6, §8, §13): brief → question →
 * tool → answer → barge-in → correction → new query → simulated engine drop.
 */
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import brief from "../../mocks/brief.json";
import tools from "../../mocks/tool-results.json";
import type { AnyEngineEvent } from "../../src/voice/types";
import { harness, ofType, runUntil, UUID, type Harness } from "./helpers";

let h: Harness;
let events: AnyEngineEvent[];

beforeAll(async () => {
  vi.useFakeTimers();
  h = harness({ script: true, dropAtEnd: true });
  void h.engine.connect({ conversationId: "conv-script" });
  await runUntil(() => h.events.some((e) => e.type === "error"));
  await vi.advanceTimersByTimeAsync(2_000);
  events = h.events;
});

afterAll(() => {
  vi.useRealTimers();
});

const STATES = ["idle", "connecting", "listening", "thinking", "speaking", "renewing", "error"];

describe("sobre del evento (docs/08 §2)", () => {
  it("todo evento trae el sobre completo", () => {
    expect(events.length).toBeGreaterThan(50);
    for (const ev of events) {
      expect(Object.keys(ev).sort()).toEqual(
        ["conversation_id", "event_id", "generation_id", "payload", "schema_version", "seq", "state_version", "t", "turn_id", "type"].sort(),
      );
      expect(ev.schema_version).toBe("1");
      expect(ev.event_id).toMatch(UUID);
      expect(ev.conversation_id).toBe("conv-script");
      expect(Number.isInteger(ev.seq)).toBe(true);
      expect(Number.isInteger(ev.state_version)).toBe(true);
      expect(typeof ev.t).toBe("number");
      expect(ev.turn_id === null || typeof ev.turn_id === "string").toBe(true);
      expect(ev.generation_id === null || typeof ev.generation_id === "string").toBe(true);
      expect(ev.payload).toBeTypeOf("object");
    }
  });

  it("event_id es único", () => {
    expect(new Set(events.map((e) => e.event_id)).size).toBe(events.length);
  });

  it("seq es estrictamente monótono y sin huecos", () => {
    events.forEach((ev, i) => expect(ev.seq).toBe(i + 1));
  });

  it("t (reloj de la sesión) y state_version nunca retroceden", () => {
    for (let i = 1; i < events.length; i++) {
      expect(events[i]!.t).toBeGreaterThanOrEqual(events[i - 1]!.t);
      expect(events[i]!.state_version).toBeGreaterThanOrEqual(events[i - 1]!.state_version);
    }
  });

  it("solo emite estados del contrato y empieza conectando", () => {
    const states = ofType(events, "status").map((e) => e.payload.state);
    for (const s of states) expect(STATES).toContain(s);
    expect(states[0]).toBe("connecting");
  });
});

describe("brief inicial (A-02, A-25)", () => {
  it("lo primero que se dice es el brief, con cifras y corte", () => {
    const first = ofType(events, "speech")[0]!;
    expect(first.payload).toMatchObject({ phase: "start", kind: "brief" });
    const text = ofType(events, "transcript").find((e) => e.generation_id === first.payload.generation_id && e.payload.final)!;
    expect(text.payload.text).toBe(brief.spoken_brief);
    expect(text.payload.text).toContain("9.320");
    expect(text.payload.text).toMatch(/noviembre de 2022/);
  });

  it("el brief dura 20 s o menos", () => {
    const [start, stop] = ofType(events, "speech").filter((e) => e.payload.kind === "brief");
    expect(stop!.payload.phase).toBe("stop");
    expect(stop!.t - start!.t).toBeLessThanOrEqual(20_000);
  });
});

describe("transcripción (docs/08 §8, A-13)", () => {
  it("por cada utterance_id llegan parciales y un único final, que es el último", () => {
    const byId = new Map<string, AnyEngineEvent[]>();
    for (const ev of ofType(events, "transcript")) {
      if (ev.payload.corrects) continue;
      byId.set(ev.payload.utterance_id, [...(byId.get(ev.payload.utterance_id) ?? []), ev]);
    }
    expect(byId.size).toBeGreaterThanOrEqual(10);
    for (const list of byId.values()) {
      const t = list as Extract<AnyEngineEvent, { type: "transcript" }>[];
      const finals = t.filter((e) => e.payload.final);
      expect(finals).toHaveLength(1);
      expect(t.at(-1)!.payload.final).toBe(true);
      expect(new Set(t.map((e) => e.payload.role)).size).toBe(1);
      expect(new Set(t.map((e) => e.payload.t_start)).size).toBe(1);
      for (let i = 1; i < t.length; i++) {
        // A partial only grows: the earlier text is a prefix of the later one.
        expect(t[i]!.payload.text.startsWith(t[i - 1]!.payload.text)).toBe(true);
      }
    }
  });

  it("los enunciados hablados del usuario tienen parciales antes del final", () => {
    const q = ofType(events, "transcript").filter((e) => e.payload.role === "user" && e.payload.text.startsWith("¿Qué"));
    expect(q.length).toBeGreaterThan(1);
    expect(q.filter((e) => !e.payload.final).length).toBeGreaterThanOrEqual(1);
    expect(q.at(-1)!.payload.text).toBe("¿Qué municipios tienen más camas?");
  });

  it("roles, marcas de tiempo y procedencia válidos", () => {
    for (const ev of ofType(events, "transcript")) {
      expect(["user", "agent"]).toContain(ev.payload.role);
      expect(["engine", "local", "arrival"]).toContain(ev.payload.t_source);
      expect(ev.payload.t_start).toBeLessThanOrEqual(ev.payload.t_end);
      expect(ev.payload.t_end).toBeLessThanOrEqual(ev.t);
    }
  });

  it("cada enunciado del usuario abre un turno nuevo y el agente responde en ese turno", () => {
    const userFinals = ofType(events, "transcript").filter((e) => e.payload.role === "user" && e.payload.final && !e.payload.corrects);
    const turns = userFinals.map((e) => e.turn_id);
    expect(turns.every((t) => typeof t === "string")).toBe(true);
    expect(new Set(turns).size).toBe(userFinals.length);
  });
});

describe("puente de herramientas (docs/08 §5, A-24)", () => {
  it("todo tool_call va seguido de su tool_result con el mismo tool_call_id", () => {
    const toolEvents = events.filter((e) => e.type === "tool_call" || e.type === "tool_result");
    expect(toolEvents.length).toBe(8);
    for (let i = 0; i < toolEvents.length; i += 2) {
      const call = toolEvents[i]!;
      const result = toolEvents[i + 1]!;
      expect(call.type).toBe("tool_call");
      expect(result.type).toBe("tool_result");
      expect((result.payload as { tool_call_id: string }).tool_call_id).toBe((call.payload as { tool_call_id: string }).tool_call_id);
      expect(result.turn_id).toBe(call.turn_id);
    }
  });

  it("tool_call_id es único y cada herramienta se ejecuta una sola vez", () => {
    const ids = ofType(events, "tool_call").map((e) => e.payload.tool_call_id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(h.toolCalls.map((c) => c.tool_call_id)).toEqual(ids);
  });

  it("el resultado trae SoQL, ms, filas, estado de caché y referencia de evidencia", () => {
    for (const ev of ofType(events, "tool_result")) {
      expect(ev.payload.status).toBe("ok");
      expect(ev.payload.trace.soql).toMatch(/^SELECT /);
      expect(ev.payload.trace.ms).toBeGreaterThan(0);
      expect(ev.payload.trace.rows).toBeGreaterThanOrEqual(1);
      expect(["live", "fresh", "stale"]).toContain(ev.payload.trace.cache_status);
      expect(ev.payload.evidence_ref).toMatch(/^sha256:/);
    }
  });

  it("antes de cada consulta de datos hay un reconocimiento previo hablado (R-29)", () => {
    for (const call of ofType(events, "tool_call").filter((e) => e.payload.name !== "correct_context")) {
      const ack = ofType(events, "speech").find((s) => s.turn_id === call.turn_id && s.payload.kind === "ack" && s.payload.phase === "stop");
      expect(ack, `turno ${call.turn_id}`).toBeDefined();
      expect(ack!.seq).toBeLessThan(call.seq);
    }
  });

  it("ninguna respuesta empieza antes de que llegue el resultado de su herramienta", () => {
    for (const call of ofType(events, "tool_call")) {
      const result = ofType(events, "tool_result").find((r) => r.payload.tool_call_id === call.payload.tool_call_id)!;
      const between = events.filter((e) => e.seq > call.seq && e.seq < result.seq);
      expect(between.filter((e) => e.type === "speech" || e.type === "transcript")).toEqual([]);
    }
  });

  it("las cifras dichas salen del sobre de evidencia", () => {
    const finals = ofType(events, "transcript").filter((e) => e.payload.role === "agent" && e.payload.final).map((e) => e.payload.text);
    const all = finals.join(" ");
    for (const g of tools.top_beds_by_municipality.data.groups) expect(all).toContain(new Intl.NumberFormat("es-CO").format(g.value));
    expect(all).toMatch(/En Melgar, Tolima hay 9 camas instaladas/);
    expect(all).toMatch(/corte a noviembre de 2022/);
  });
});

describe("interrupción y texto realmente escuchado (docs/08 §6, A-11)", () => {
  const interrupted = () => ofType(events, "interrupted");

  it("hay exactamente una interrupción, sobre una generación que estaba hablando", () => {
    expect(interrupted()).toHaveLength(1);
    const ev = interrupted()[0]!;
    const start = ofType(events, "speech").find((s) => s.payload.generation_id === ev.payload.generation_id && s.payload.phase === "start");
    expect(start).toBeDefined();
    expect(start!.seq).toBeLessThan(ev.seq);
    expect(ev.payload.played_ms).toBeGreaterThan(0);
  });

  it("delivered_text es un prefijo estrictamente más corto que el texto generado", () => {
    const ev = interrupted()[0]!;
    const generated = ofType(events, "transcript")
      .filter((t) => t.generation_id === ev.payload.generation_id)
      .map((t) => t.payload.text)
      .sort((a, b) => b.length - a.length)[0]!;
    expect(ev.payload.delivered_text.length).toBeGreaterThan(0);
    expect(ev.payload.delivered_text.length).toBeLessThan(generated.length);
    expect(generated.startsWith(ev.payload.delivered_text)).toBe(true);
  });

  it("played_ms es coherente con el tiempo que la generación llevaba hablando", () => {
    const ev = interrupted()[0]!;
    const start = ofType(events, "speech").find((s) => s.payload.generation_id === ev.payload.generation_id && s.payload.phase === "start")!;
    expect(ev.payload.played_ms).toBeLessThanOrEqual(ev.t - start.t);
  });

  it("no llega ningún evento posterior con el generation_id interrumpido (docs/08 §6.5)", () => {
    const ev = interrupted()[0]!;
    const late = events.filter((e) => e.seq > ev.seq && e.generation_id === ev.payload.generation_id);
    expect(late.map((e) => `${e.seq}:${e.type}`)).toEqual([]);
  });

  it("tras interrumpir no se emite más texto del agente para esa generación", () => {
    const ev = interrupted()[0]!;
    const late = ofType(events, "transcript").filter((e) => e.seq > ev.seq && e.generation_id === ev.payload.generation_id);
    expect(late.map((e) => e.payload.text)).toEqual([]);
  });

  it("el turno interrumpido reporta la parada de reproducción en latency", () => {
    const ev = interrupted()[0]!;
    const lat = ofType(events, "latency").find((l) => l.turn_id === ev.turn_id);
    expect(lat?.payload.t_playback_stop).toBeTypeOf("number");
  });

  it("una sola generación habla a la vez (R-24)", () => {
    let open: string | null = null;
    for (const s of ofType(events, "speech")) {
      if (s.payload.phase === "start") {
        expect(open, `empieza ${s.payload.generation_id} con ${open} abierta`).toBeNull();
        open = s.payload.generation_id;
      } else {
        expect(s.payload.generation_id).toBe(open);
        open = null;
      }
    }
    expect(open).toBeNull();
  });
});

describe("corrección (docs/08 §8, A-09)", () => {
  const correction = () => ofType(events, "transcript").find((e) => e.payload.corrects)!;

  it("la corrección apunta con `corrects` al enunciado original, que se conserva", () => {
    const fix = correction();
    expect(fix).toBeDefined();
    expect(fix.payload.final).toBe(true);
    expect(fix.payload.text).toMatch(/Melgar/);
    const original = ofType(events, "transcript").filter((e) => e.payload.utterance_id === fix.payload.corrects);
    expect(original.at(-1)!.payload.text).toBe("¿Cuántas camas hay en Medellín?");
    expect(original.every((e) => e.seq < fix.seq)).toBe(true);
    expect(fix.payload.utterance_id).not.toBe(fix.payload.corrects);
  });

  it("correct_context señala el turno corregido y sube state_version", () => {
    const fix = correction();
    const originalTurn = ofType(events, "transcript").find((e) => e.payload.utterance_id === fix.payload.corrects)!.turn_id;
    const call = ofType(events, "tool_call").find((e) => e.payload.name === "correct_context")!;
    expect(call.seq).toBeGreaterThan(fix.seq);
    expect(call.payload.args).toMatchObject({ target_turn_id: originalTurn, field: "municipality", value: "Melgar" });
    expect(call.payload.args.expected_state_version).toBe(call.state_version);
    const result = ofType(events, "tool_result").find((e) => e.payload.tool_call_id === call.payload.tool_call_id)!;
    expect(result.state_version).toBe(call.state_version + 1);
  });

  it("la consulta siguiente usa la localidad corregida, no la original", () => {
    const calls = ofType(events, "tool_call");
    const fixAt = calls.findIndex((e) => e.payload.name === "correct_context");
    const next = calls[fixAt + 1]!;
    expect(next.payload.name).toBe("aggregate_ips");
    expect(JSON.stringify(next.payload.args)).toMatch(/MELGAR/);
    expect(calls.slice(fixAt + 1).some((c) => /MEDELL/.test(JSON.stringify(c.payload.args)))).toBe(false);
  });
});

describe("latencia (docs/08 §9)", () => {
  it("las marcas de cada turno están en orden", () => {
    const lats = ofType(events, "latency");
    expect(lats.length).toBeGreaterThanOrEqual(3);
    for (const { payload: p } of lats) {
      const chain = [p.t_speech_end, p.t_ack_audio, p.t_tool_start, p.t_tool_end, p.t_first_useful_audio].filter(
        (v): v is number => v !== undefined,
      );
      for (let i = 1; i < chain.length; i++) expect(chain[i]!).toBeGreaterThanOrEqual(chain[i - 1]!);
    }
  });

  it("el reconocimiento previo se mide aparte y llega en 1 s o menos (docs/07 §8)", () => {
    for (const { payload: p } of ofType(events, "latency")) {
      if (p.t_ack_audio === undefined) continue;
      expect(p.t_ack_audio - p.t_speech_end).toBeLessThanOrEqual(1_000);
      expect(p.t_first_useful_audio ?? Infinity).toBeGreaterThan(p.t_ack_audio);
    }
  });
});

describe("corte simulado del motor (A-23)", () => {
  it("el guion termina con ENGINE_DROPPED reintentable y sin eventos posteriores", () => {
    const last = events.at(-1)!;
    expect(last.type).toBe("error");
    expect(last.payload).toMatchObject({ code: "ENGINE_DROPPED", retryable: true });
  });
});
