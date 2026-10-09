/**
 * Controller + store + scripted engine, end to end without a browser
 * (docs/08 §5, §7, §13; A-16, A-23, A-25): the session-level stream of events.
 *
 * `store.dispatch` is wrapped so the test sees exactly what the store receives,
 * from the engines and from the controller itself.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnyEngineEvent } from "../../src/voice/types";
import { ofType, runUntil, UUID } from "./helpers";

const seen = vi.hoisted(() => ({ events: [] as unknown[] }));

vi.mock("../../src/voice/store", async (original) => {
  const real = await original<typeof import("../../src/voice/store")>();
  return {
    ...real,
    dispatch: (ev: Parameters<typeof real.dispatch>[0]) => {
      if (ev.conversation_id === real.getState().conversation_id) seen.events.push(ev);
      real.dispatch(ev);
    },
  };
});

const controller = await import("../../src/voice/controller");
const store = await import("../../src/voice/store");

const events = (): AnyEngineEvent[] => seen.events as AnyEngineEvent[];
const session = () => ofType(events(), "session");

beforeEach(() => {
  vi.useFakeTimers();
  controller.restart();
  if (store.getState().engine !== "openai") controller.selectEngine("openai");
  seen.events.length = 0;
});

afterEach(() => {
  controller.restart();
  vi.useRealTimers();
});

/** Plays the whole script and the automatic switch that follows the simulated drop. */
async function playScript(): Promise<void> {
  void controller.start();
  await runUntil(() => session().length > 0);
  await runUntil(() => store.getState().status === "listening");
}

describe("guion completo con corte del motor (A-23)", () => {
  it("emite un evento `session` con el sobre completo al cambiar de motor", async () => {
    await playScript();
    expect(session()).toHaveLength(1);
    const ev = session()[0]!;
    expect(ev.payload).toMatchObject({ event: "switched", from: "openai", to: "gemini", attempt: 1 });
    expect(ev.payload.reason).toMatch(/ENGINE_DROPPED/);
    expect(ev.schema_version).toBe("1");
    expect(ev.event_id).toMatch(UUID);
    expect(ev.conversation_id).toBe(store.getState().conversation_id);
    expect(typeof ev.seq).toBe("number");
    expect(typeof ev.t).toBe("number");
  });

  it("el cambio es único, avisa «sesión renovada» y el HUD pasa al otro motor", async () => {
    await playScript();
    await vi.advanceTimersByTimeAsync(30_000);
    const s = store.getState();
    expect(session()).toHaveLength(1);
    expect(s.engine).toBe("gemini");
    expect(s.model).toMatch(/gemini/i);
    expect(s.running).toBe(true);
    const notice = s.notices.find((n) => n.kind === "session");
    expect(notice?.text).toMatch(/Sesión renovada: motor cambiado a Gemini Live/);
    expect(s.turns.at(-1)!.attempts).toBe(2);
  });

  it("no repite ninguna consulta ni vuelve a decir el brief tras el cambio", async () => {
    await playScript();
    const at = session()[0]!;
    const index = events().indexOf(at);
    const before = events().slice(0, index);
    const after = events().slice(index);
    expect(ofType(before, "tool_call")).toHaveLength(4);
    expect(ofType(after, "tool_call")).toEqual([]);
    expect(ofType(after, "speech")).toEqual([]);
    expect(store.getState().tools).toHaveLength(4);
    expect(store.getState().tools.every((t) => t.status === "ok")).toBe(true);
  });

  it("la conversación y la evidencia sobreviven al cambio y el motor nuevo responde (A-16)", async () => {
    await playScript();
    const utterances = store.getState().utterances.length;
    controller.sendText("¿Cuántas camas hay en total?");
    await runUntil(() => store.getState().tools.length === 5 && store.getState().status === "listening");
    const s = store.getState();
    expect(s.utterances.length).toBeGreaterThan(utterances);
    expect(s.utterances.at(-1)!.text).toContain("97.036");
    expect(s.turns.at(-1)!.engine).toBe("gemini");
    expect(s.turns.slice(0, -1).every((t) => t.engine === "openai")).toBe(true);
  });

  it("el reloj de la sesión no se reinicia al cambiar de motor", async () => {
    await playScript();
    controller.sendText("¿Cuántas camas hay en total?");
    await runUntil(() => store.getState().tools.length === 5);
    const ts = events().map((e) => e.t);
    for (let i = 1; i < ts.length; i++) expect(ts[i]!).toBeGreaterThanOrEqual(ts[i - 1]!);
  });

  it("seq es monótono en toda la sesión, también a través del cambio de motor (docs/08 §2)", async () => {
    await playScript();
    controller.sendText("¿Cuántas camas hay en total?");
    await runUntil(() => store.getState().tools.length === 5);
    const seqs = events().map((e) => e.seq);
    const backwards = seqs.filter((s, i) => i > 0 && s <= seqs[i - 1]!);
    expect(backwards.length, `seq retrocede ${backwards.length} veces; p. ej. ${seqs.slice(-12).join(",")}`).toBe(0);
  });

  it("el guion deja corrección, texto no escuchado y evidencia invalidada en el estado (A-09, A-11)", async () => {
    await playScript();
    const s = store.getState();
    const asked = s.utterances.find((u) => u.text === "¿Cuántas camas hay en Medellín?")!;
    expect(asked.correction?.text).toBe("¿Cuántas camas hay en Melgar?");
    const cut = s.utterances.find((u) => u.delivered_text !== undefined)!;
    expect(cut.role).toBe("agent");
    expect(cut.final).toBe(true);
    expect(cut.text.length).toBeGreaterThan(cut.delivered_text!.length);
    const invalidated = s.tools.filter((t) => t.invalidated);
    expect(invalidated).toHaveLength(1);
    expect(JSON.stringify(invalidated[0]!.args)).toMatch(/MEDELL/);
    expect(s.turns.find((t) => t.interrupted_at !== null)?.stop_ms).toBeLessThanOrEqual(200);
  });

  it("cada turno tiene su estimación de afecto, rotulada por método (A-13, A-14)", async () => {
    await playScript();
    await vi.advanceTimersByTimeAsync(3_000);
    const s = store.getState();
    expect(s.affect.length).toBe(s.turns.length);
    // Voice analysis is ON by default: a turn is labelled "text", or "voice"/"fused" when the clip was used.
    expect(s.affect.every((a) => ["text", "voice", "fused"].includes(a.estimate.method) && a.estimate.confidence === null)).toBe(true);
    // Turned off, every reading falls back to the text channel.
    controller.restart();
    store.setVoiceAnalysis(false);
    await playScript();
    await vi.advanceTimersByTimeAsync(3_000);
    const off = store.getState();
    expect(off.affect.length).toBe(off.turns.length);
    expect(off.affect.every((a) => a.estimate.method === "text")).toBe(true);
    store.setVoiceAnalysis(true);
  });
});

describe("controles (docs/08 §10)", () => {
  it("cambiar de motor en el selector durante la sesión emite `switched` sin consumir intentos", async () => {
    void controller.start({ question: "¿Cuántas camas hay en total?" });
    await runUntil(() => store.getState().tools.length === 1 && store.getState().status === "listening");
    controller.selectEngine("gemini");
    await runUntil(() => session().length === 1);
    expect(session()[0]!.payload).toMatchObject({ event: "switched", from: "openai", to: "gemini", attempt: 0 });
    expect(store.getState().tools).toHaveLength(1);
    expect(store.getState().turns.at(-1)!.attempts).toBe(1);
  });

  it("cambiar de motor con la sesión detenida no emite eventos, solo cambia el ajuste", () => {
    controller.selectEngine("gemini");
    expect(events()).toEqual([]);
    expect(store.getState()).toMatchObject({ engine: "gemini", running: false });
  });

  it("«Más directo» es una preferencia explícita con motivo, y se puede quitar (A-22)", () => {
    controller.toggleDirect();
    expect(store.getState().style).toMatchObject({ style: "directo", source: "preference" });
    expect(store.getState().style.reason.length).toBeGreaterThan(10);
    controller.toggleDirect();
    expect(store.getState().style.style).toBe("neutro");
  });

  it("«Más directo» acorta la respuesta siguiente sin cambiar la cifra (A-14)", async () => {
    void controller.start({ question: "¿Cuántas camas hay en total?" });
    await runUntil(() => store.getState().tools.length === 1 && store.getState().status === "listening");
    const long = store.getState().utterances.at(-1)!.text;
    controller.toggleDirect();
    controller.sendText("¿Cuántas camas hay en total?");
    await runUntil(() => store.getState().tools.length === 2 && store.getState().status === "listening");
    const short = store.getState().utterances.at(-1)!.text;
    expect(short.length).toBeLessThan(long.length);
    expect(long).toContain("97.036");
    expect(short).toContain("97.036");
  });

  it("«Corregir lo que dije» conserva el original, invalida su evidencia y vuelve a consultar (A-09)", async () => {
    void controller.start({ question: "¿Cuántas camas hay en Medellín?" });
    await runUntil(() => store.getState().tools.length === 1 && store.getState().status === "listening");
    const original = store.getState().utterances.find((u) => u.role === "user")!;
    controller.correct(original.id, "¿Cuántas camas hay en Melgar?");
    await runUntil(() => store.getState().tools.length === 2 && store.getState().status === "listening");
    const s = store.getState();
    const fix = ofType(events(), "transcript").find((e) => e.payload.corrects)!;
    expect(fix.payload.corrects).toBe(original.id);
    expect(s.utterances.find((u) => u.id === original.id)).toMatchObject({
      text: "¿Cuántas camas hay en Medellín?",
      correction: { text: "¿Cuántas camas hay en Melgar?" },
    });
    expect(s.tools[0]!.invalidated).toBe(true);
    expect(s.tools[1]!.invalidated).toBe(false);
    expect(JSON.stringify(s.tools[1]!.args)).toMatch(/MELGAR/);
    expect(s.utterances.at(-1)!.text).toMatch(/Melgar, Tolima hay 9 camas/);
  });

  it("«Reconsultar» repite la llamada en vivo y el resultado coincide (A-24)", async () => {
    void controller.start({ question: "¿Cuántas IPS hay en Bogotá?" });
    await runUntil(() => store.getState().tools.length === 1 && store.getState().status === "listening");
    const id = store.getState().tools[0]!.tool_call_id;
    const done = controller.requery(id);
    expect(store.getState().tools[0]!.requery).toEqual({ pending: true });
    await vi.advanceTimersByTimeAsync(2_000);
    await done;
    expect(store.getState().tools[0]!.requery).toMatchObject({ pending: false, matches: true });
    expect(store.getState().tools).toHaveLength(1);
  });

  it("«Reiniciar» detiene el motor y borra el estado; no llega nada después (A-25)", async () => {
    void controller.start();
    await vi.advanceTimersByTimeAsync(12_000);
    expect(store.getState().utterances.length).toBeGreaterThan(0);
    controller.restart();
    seen.events.length = 0;
    await vi.advanceTimersByTimeAsync(60_000);
    const s = store.getState();
    expect(s).toMatchObject({ running: false, status: "idle", conversation_id: null });
    expect([s.utterances, s.tools, s.affect, s.turns, s.notices]).toEqual([[], [], [], [], []]);
    expect(events()).toEqual([]);
  });

  it("«Detener» conserva la transcripción y corta los eventos", async () => {
    void controller.start();
    await vi.advanceTimersByTimeAsync(12_000);
    controller.stop();
    const count = store.getState().utterances.length;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(store.getState()).toMatchObject({ running: false, status: "idle" });
    expect(store.getState().utterances.length).toBe(count);
    expect(count).toBeGreaterThan(0);
  });

  it("una pregunta hecha antes de iniciar arranca la sesión y se responde tras el brief", async () => {
    controller.sendText("¿Cuántas IPS hay en Bogotá?");
    await runUntil(() => store.getState().tools.length === 1 && store.getState().status === "listening");
    const s = store.getState();
    expect(s.utterances[0]!.kind).toBe("brief");
    expect(s.utterances.find((u) => u.role === "user")!.text).toBe("¿Cuántas IPS hay en Bogotá?");
    expect(s.utterances.at(-1)!.text).toContain("1.270");
  });
});
