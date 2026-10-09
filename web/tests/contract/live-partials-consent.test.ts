/**
 * Live transcription, voice consent and tool output of the real-engine core
 * (docs/08 §2, §5; docs/10 §6, R-26). The provider transport, the player and the
 * microphone are stubbed: no browser, no network.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const { micAcquire } = vi.hoisted(() => ({ micAcquire: vi.fn(async () => undefined) }));
vi.mock("../../src/voice/audio/mic-tap", () => {
  class MicError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  }
  const tap = { acquire: micAcquire, release: vi.fn(), onFrame: vi.fn(() => () => undefined), lastVoiceAt: null, active: false };
  return { MicError, getMicTap: () => tap };
});
vi.mock("../../src/voice/audio/player", () => {
  const player = {
    attach: () => () => undefined,
    resume: async () => true,
    flush: () => new Map<string, number>(),
    enqueue: () => 0,
    playedMs: () => 0,
    audibleGeneration: null,
  };
  return { getPlayer: () => player };
});
vi.mock("../../src/voice/api", async (orig) => ({
  ...(await orig<typeof import("../../src/voice/api")>()),
  requestRealtimeSession: async () => ({ engine: "openai", model: "test", connect: { url: "wss://x", token: "t" } }),
}));

import { RealtimeEngineBase, toolOutputForModel } from "../../src/voice/realtime-base";
import { MOCK_BRIEF } from "../../src/voice/api";
import * as store from "../../src/voice/store";
import { readConsent, writeConsent, CONSENT_KEY } from "../../src/scripts/analysis";
import { markFigures, parseSpokenNumber } from "../../src/scripts/figures";
import type { AnyEngineEvent, EngineEvents, EvidenceEnvelope } from "../../src/voice/types";

class TestEngine extends RealtimeEngineBase {
  readonly id = "openai" as const;
  protected readonly inputRate = 24_000 as const;
  sent: string[] = [];
  private open = false;
  protected async openTransport(): Promise<void> {
    this.open = true;
  }
  protected closeTransport(): void {
    this.open = false;
  }
  protected get transportReady(): boolean {
    return this.open;
  }
  protected dropTransportForTest(): void {}
  protected sendAudioFrame(): void {}
  protected sendUserText(text: string): void {
    this.sent.push(`user:${text}`);
  }
  protected sendGreeting(): void {}
  protected sendToolOutput(): void {}
  protected sendNote(text: string): void {
    this.sent.push(`note:${text}`);
  }
  protected sendSeed(): void {}
  protected sendStyle(): void {}
  protected cancelGeneration(): void {}
  // Expose the provider reducers to the test.
  userStart(key: string): void {
    this.userSpeechStarted(key);
  }
  userText(key: string, text: string, final: boolean, append = !final): void {
    this.userTranscript(key, text, { final, append });
  }
  agentStart(id: string): void {
    this.generationStarted(id);
  }
  agentText(id: string, text: string, final: boolean): void {
    this.agentTranscript(id, text, { final, append: !final });
  }
}

const transcripts = (events: AnyEngineEvent[]): EngineEvents["transcript"][] =>
  events.filter((e) => e.type === "transcript").map((e) => e.payload as EngineEvents["transcript"]);

function make(micAllowed?: () => boolean): { engine: TestEngine; events: AnyEngineEvent[] } {
  const t0 = Date.now();
  const engine = new TestEngine({
    now: () => Date.now() - t0,
    getBrief: async () => ({ ...MOCK_BRIEF, spoken_brief: "" }),
    runTool: async () => {
      throw new Error("not used");
    },
    micAllowed,
  });
  const events: AnyEngineEvent[] = [];
  engine.on("transcript", (ev) => events.push(ev as AnyEngineEvent));
  engine.on("error", (ev) => events.push(ev as AnyEngineEvent));
  return { engine, events };
}

beforeEach(() => micAcquire.mockClear());

describe("live partial transcripts (docs/08 §2)", () => {
  it("user deltas grow one utterance in place, then finalize", () => {
    const { engine, events } = make();
    engine.userStart("item-1");
    engine.userText("item-1", "¿Cuántas ", false);
    engine.userText("item-1", "IPS hay?", false);
    engine.userText("item-1", "¿Cuántas IPS hay?", true);
    const t = transcripts(events);
    expect(t.map((p) => [p.text.trim(), p.final])).toEqual([
      ["¿Cuántas", false],
      ["¿Cuántas IPS hay?", false],
      ["¿Cuántas IPS hay?", true],
    ]);
    expect(new Set(t.map((p) => p.utterance_id)).size).toBe(1);
  });

  it("agent deltas share one utterance_id and end with one final", () => {
    const { engine, events } = make();
    engine.agentStart("resp-1");
    engine.agentText("resp-1", "Hay ", false);
    engine.agentText("resp-1", "97.036 camas.", false);
    engine.agentText("resp-1", "Hay 97.036 camas.", true);
    const t = transcripts(events);
    expect(t.map((p) => p.final)).toEqual([false, false, true]);
    expect(t.at(-1)?.text).toBe("Hay 97.036 camas.");
    expect(new Set(t.map((p) => p.utterance_id)).size).toBe(1);
  });

  it("the store updates the same bubble for partials (no duplicates)", async () => {
    store.beginSession("conv-p", "openai", "m", false);
    const base = { schema_version: "1" as const, conversation_id: "conv-p", turn_id: "t1", state_version: 1, generation_id: "g1", seq: 0 };
    for (const [text, final] of [["Hay", false], ["Hay 12", false], ["Hay 12 IPS.", true]] as const) {
      store.dispatch({
        ...base,
        event_id: crypto.randomUUID(),
        t: 1,
        type: "transcript",
        payload: { role: "agent", utterance_id: "a1", text, final, t_start: 0, t_end: 1, t_source: "engine" },
      });
    }
    const agent = store.getState().utterances.filter((u) => u.role === "agent");
    expect(agent).toHaveLength(1);
    expect(agent[0]).toMatchObject({ text: "Hay 12 IPS.", final: true });
  });
});

describe("explicit voice consent (R-26)", () => {
  it("the microphone is not opened without consent", async () => {
    const { engine } = make(() => false);
    await engine.connect({ conversationId: "c1" });
    expect(micAcquire).not.toHaveBeenCalled();
    await engine.disconnect();
  });

  it("consent opens it mid-session; with consent it opens on connect", async () => {
    const { engine } = make(() => false);
    await engine.connect({ conversationId: "c2" });
    await engine.setMicEnabled(true);
    expect(micAcquire).toHaveBeenCalledTimes(1);
    await engine.disconnect();

    const other = make(() => true);
    await other.engine.connect({ conversationId: "c3" });
    expect(micAcquire).toHaveBeenCalledTimes(2);
    await other.engine.disconnect();
  });

  it("the store starts without voice analysis; consent is read only from an explicit 'on'", () => {
    store.reset();
    expect(store.getState().voiceAnalysis).toBe(false);
    const mem = new Map<string, string>();
    const storage = {
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => void mem.set(k, v),
      removeItem: (k: string) => void mem.delete(k),
    };
    expect(readConsent(storage)).toBe(false);
    writeConsent(storage, true);
    expect(mem.get(CONSENT_KEY)).toBe("on");
    expect(readConsent(storage)).toBe(true);
    writeConsent(storage, false);
    expect(readConsent(storage)).toBe(false);
    const broken = { getItem: () => { throw new Error("blocked"); } };
    expect(readConsent(broken)).toBe(false);
    expect(readConsent(null)).toBe(false);
  });
});

describe("tool output to the engine (docs/09 §5)", () => {
  const env = (over: Partial<EvidenceEnvelope>): EvidenceEnvelope =>
    ({
      schema_version: "1",
      tool_call_id: "c",
      turn_id: "t",
      state_version: 1,
      status: "ok",
      data: { value: 12, rows: [1, 2, 3] },
      evidence: { dataset_id: "d", source_url: "", query_fingerprint: "f", cutoff_raw: "2022", fetched_at: "", cache_status: "live", complete: true, unit: "IPS", filters: {}, warnings: [] },
      trace: { engine: "soda3", soql: "", ms: 1, rows: 1 },
      error: null,
      next_cursor: null,
      context_patch: {},
      ...over,
    }) as EvidenceEnvelope;

  it("sends only {status, for_model} when the backend gives grounded text", () => {
    expect(toolOutputForModel(env({ for_model: "Hay 12 IPS (corte 2022)." }))).toEqual({ status: "ok", for_model: "Hay 12 IPS (corte 2022)." });
  });

  it("adds the error, and falls back to the compact data without for_model", () => {
    const out = toolOutputForModel(env({ status: "unavailable", for_model: "Sin datos.", error: { code: "TIMEOUT", message: "plazo" } }));
    expect(out).toEqual({ status: "unavailable", for_model: "Sin datos.", error: { code: "TIMEOUT", message: "plazo" } });
    expect(toolOutputForModel(env({}))).toHaveProperty("data");
  });
});

describe("figure check marks (docs/10 §5)", () => {
  it("parses es-CO figures and marks only the unsupported ones", () => {
    expect(parseSpokenNumber("97.036")).toBe(97036);
    expect(parseSpokenNumber("12,5")).toBe(12.5);
    expect(parseSpokenNumber("1234.")).toBe(1234);
    const html = markFigures("Hay 97.036 camas y 12 IPS.", [12]);
    expect(html).toBe('Hay 97.036 camas y <mark class="unverified" title="Cifra no verificada">12</mark> IPS.');
    expect(markFigures("Hay 5", undefined)).toBe("Hay 5");
  });
});
