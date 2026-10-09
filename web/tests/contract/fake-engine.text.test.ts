/**
 * Text mode and controls of the scripted engine (F-12; docs/07 §7 A-05, A-08, A-12, A-14).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import brief from "../../mocks/brief.json";
import type { ContextEnvelope, EvidenceEnvelope, StyleDecision } from "../../src/voice/types";
import { answers, ask, connected, harness, lastStatus, ofType, runUntil } from "./helpers";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

const DIRECT: StyleDecision = { style: "directo", directives: [], reason: "test", source: "preference", applies_from_turn: 2 };

describe("preguntas sugeridas (A-02)", () => {
  it.each(brief.suggested_questions)("«%s» se responde con una consulta y una cifra de la fuente", async (q) => {
    const h = harness();
    await connected(h);
    const evs = await ask(h, q);
    const results = ofType(evs, "tool_result");
    expect(results).toHaveLength(1);
    expect(results[0]!.payload.status).toBe("ok");
    const [answer] = answers(evs);
    expect(answer).toMatch(/\d/);
    expect(answer).not.toMatch(/motor simulado/);
    const user = ofType(evs, "transcript").find((e) => e.payload.role === "user")!;
    expect(user.payload).toMatchObject({ text: q, final: true, t_source: "local" });
  });
});

describe("semántica de la respuesta", () => {
  it("«¿cuántos prestadores hay?» cuenta prestadores distintos, no filas (A-05)", async () => {
    const h = harness();
    await connected(h);
    const evs = await ask(h, "¿Cuántos prestadores hay?");
    const [answer] = answers(evs);
    expect(answer).toContain("9.320");
    expect(answer).not.toContain("41.427");
    expect(h.toolCalls[0]!.args).toMatchObject({ metric: "provider_count" });
  });

  it("una pregunta con un municipio que el guion no cubre no devuelve el total nacional", async () => {
    const h = harness();
    await connected(h);
    const evs = await ask(h, "¿Cuántas IPS hay en Medellín?");
    const [answer] = answers(evs);
    // 9.320 is the national figure: saying it for Medellín is a wrong fact.
    expect(answer).not.toContain("9.320");
    expect(h.toolCalls.filter((c) => JSON.stringify(c.args.filters ?? {}) === "{}")).toEqual([]);
  });

  it("disponibilidad de hoy: límite honesto, sin consulta y sin cifra inventada (A-08)", async () => {
    const h = harness();
    await connected(h);
    const evs = await ask(h, "¿Hay cama disponible hoy?");
    expect(ofType(evs, "tool_call")).toEqual([]);
    const [answer] = answers(evs);
    expect(answer).toMatch(/no tiene disponibilidad/);
    expect(answer!.replace(/2022/g, "")).not.toMatch(/\d/);
  });

  it("«la más cercana»: la fuente no tiene geolocalización (A-08)", async () => {
    const h = harness();
    await connected(h);
    const [answer] = answers(await ask(h, "¿Cuál es la IPS más cercana?"));
    expect(answer).toMatch(/geolocalización|ubicación/);
  });

  it("fuera del guion: lo dice y no inventa una cifra", async () => {
    const h = harness();
    await connected(h);
    const evs = await ask(h, "¿Cuál es el teléfono del Hospital San José?");
    expect(ofType(evs, "tool_call")).toEqual([]);
    expect(answers(evs)[0]).not.toMatch(/\d/);
  });
});

describe("fuente no disponible (A-12, A-18)", () => {
  const unavailable = async (call: { tool_call_id: string }, ctx: { turn_id: string; state_version: number }): Promise<EvidenceEnvelope> => ({
    schema_version: "1",
    tool_call_id: call.tool_call_id,
    turn_id: ctx.turn_id,
    state_version: ctx.state_version,
    status: "unavailable",
    data: null,
    evidence: {
      dataset_id: "s2ru-bqt6",
      source_url: "",
      query_fingerprint: `unavailable:${call.tool_call_id}`,
      cutoff_raw: "",
      fetched_at: new Date().toISOString(),
      cache_status: "live",
      complete: false,
      unit: "",
      filters: {},
      warnings: [],
    },
    trace: { engine: "soda3", soql: "", ms: 6000, rows: 0 },
    error: { code: "TIMEOUT", message: "La consulta superó el plazo de 6 s.", retryable: true },
    next_cursor: null,
    context_patch: {},
  });

  it("si la herramienta falla, no se dice ninguna cifra y la consulta no se repite sola", async () => {
    const h = harness({}, "openai", unavailable);
    await connected(h);
    const evs = await ask(h, "¿Cuántas camas hay en total?");
    expect(ofType(evs, "tool_result")[0]!.payload.status).toBe("unavailable");
    const [answer] = answers(evs);
    expect(answer).toMatch(/No pude consultar la fuente/);
    expect(answer).not.toMatch(/\d/);
    expect(h.toolCalls).toHaveLength(1);
  });
});

describe("estilo «Más directo» (A-14, A-22)", () => {
  it("la respuesta siguiente es más breve y la cifra no cambia", async () => {
    const h = harness();
    await connected(h);
    const [long] = answers(await ask(h, "¿Cuántas camas hay en total?"));
    h.engine.applyStyle(DIRECT);
    const [short] = answers(await ask(h, "¿Cuántas camas hay en total?"));
    expect(short!.length).toBeLessThan(long!.length / 2);
    expect(long).toContain("97.036");
    expect(short).toContain("97.036");
    expect(short).toMatch(/Corte REPS: noviembre de 2022/);
  });
});

describe("Repetir (F-12)", () => {
  it("vuelve a decir la última respuesta sin consultar otra vez", async () => {
    const h = harness();
    await connected(h);
    const [first] = answers(await ask(h, "¿Cuántas IPS hay en Bogotá?"));
    const evs = await ask(h, "Repite la última respuesta, por favor.");
    expect(ofType(evs, "tool_call")).toEqual([]);
    expect(answers(evs)[0]).toBe(first);
    expect(h.toolCalls).toHaveLength(1);
  });

  it("sin respuesta previa lo dice en vez de inventar", async () => {
    const h = harness();
    await connected(h);
    const [answer] = answers(await ask(h, "Repite la última respuesta, por favor."));
    expect(answer).toMatch(/no he dado ninguna respuesta/);
  });
});

describe("interrupciones en modo texto (docs/08 §6)", () => {
  it("interrupt() corta la respuesta: delivered_text más corto, vuelve a escuchar y calla", async () => {
    const h = harness();
    await connected(h);
    h.engine.sendText("¿Cuántas camas hay en total?");
    await runUntil(() => ofType(h.events, "speech").some((s) => s.payload.kind === "answer"));
    await vi.advanceTimersByTimeAsync(700);
    h.engine.interrupt(0);
    const cut = ofType(h.events, "interrupted")[0]!;
    expect(cut.payload.played_ms).toBeGreaterThan(0);
    expect(cut.payload.delivered_text.split(/\s+/).length).toBeGreaterThanOrEqual(3);
    expect(lastStatus(h.events)).toBe("listening");
    const count = h.events.length;
    await vi.advanceTimersByTimeAsync(20_000);
    expect(h.events.length).toBe(count);
  });

  it("un texto nuevo mientras el agente habla interrumpe y abre otro turno", async () => {
    const h = harness();
    await connected(h);
    h.engine.sendText("¿Cuántas camas hay en total?");
    await runUntil(() => ofType(h.events, "speech").some((s) => s.payload.kind === "answer"));
    await vi.advanceTimersByTimeAsync(500);
    const before = h.events.at(-1)!.turn_id;
    const evs = await ask(h, "¿Cuántas IPS hay en Bogotá?");
    expect(evs[0]!.type).toBe("interrupted");
    const user = ofType(evs, "transcript").find((e) => e.payload.role === "user")!;
    expect(user.turn_id).not.toBe(before);
    expect(answers(evs).at(-1)).toContain("1.270");
  });

  it("un texto nuevo durante una consulta en curso no deja un tool_call sin tool_result", async () => {
    const h = harness();
    await connected(h);
    h.engine.sendText("¿Cuántas camas hay en total?");
    await runUntil(() => ofType(h.events, "tool_call").length === 1);
    await ask(h, "¿Cuántas IPS hay en Bogotá?");
    const calls = ofType(h.events, "tool_call").map((e) => e.payload.tool_call_id);
    const results = ofType(h.events, "tool_result").map((e) => e.payload.tool_call_id);
    expect(results).toEqual(calls);
  });

  it("interrupt() sin nadie hablando no emite nada", async () => {
    const h = harness();
    await connected(h);
    const count = h.events.length;
    h.engine.interrupt(0);
    expect(h.events.length).toBe(count);
  });
});

describe("ciclo de vida", () => {
  it("sendText antes de conectar no emite eventos", () => {
    const h = harness();
    h.engine.sendText("hola");
    expect(h.events).toEqual([]);
  });

  it("disconnect() detiene todo: no llegan eventos tardíos", async () => {
    const h = harness({ script: true, dropAtEnd: true });
    void h.engine.connect({ conversationId: "conv-test" });
    await vi.advanceTimersByTimeAsync(3_000);
    await h.engine.disconnect("user_stop");
    const count = h.events.length;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(h.events.length).toBe(count);
  });

  it("al conectar con semilla renueva sin repetir el brief ni ejecutar herramientas (A-23)", async () => {
    const seed: ContextEnvelope = {
      instructions_version: "reto01-ips-v1",
      state: { conversation_id: "conv-test", state_version: 3, confirmed_filters: {}, selected_site_keys: [], pending_candidates: [], tone_preference: "neutral" },
      summary: "",
      recent_turns: [
        { role: "user", text: "¿Cuántas camas hay en Melgar?" },
        { role: "agent", text: "En Melgar, Tolima hay 9 camas instaladas." },
      ],
      tool_results: [],
      allowed_tools: ["aggregate_ips"],
    };
    const h = harness({}, "gemini");
    const done = h.engine.connect({ conversationId: "conv-test", seed });
    await vi.advanceTimersByTimeAsync(2_000);
    await done;
    expect(ofType(h.events, "status").map((e) => e.payload.state)).toEqual(["renewing", "listening"]);
    expect(ofType(h.events, "speech")).toEqual([]);
    expect(h.toolCalls).toEqual([]);
    expect(h.events.every((e) => e.state_version === 3)).toBe(true);
    // The seeded context is usable: «Repetir» replays the last heard answer.
    const evs = await ask(h, "Repite la última respuesta, por favor.");
    expect(answers(evs)[0]).toBe("En Melgar, Tolima hay 9 camas instaladas.");
  });
});
