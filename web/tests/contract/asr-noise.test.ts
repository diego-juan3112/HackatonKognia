/**
 * Ambient noise turned into text by the provider's recognizer («公主。») must not
 * become a user turn: no bubble, no spoken answer, no analysis. The real OpenAI
 * and Gemini adapters run against a stubbed WebSocket, the controller and the
 * store are real; player, microphone and session grant are stubbed (no network).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { enqueue, duck, flush } = vi.hoisted(() => ({
  enqueue: vi.fn(() => 0),
  duck: vi.fn(),
  flush: vi.fn(() => new Map<string, number>()),
}));
vi.mock("../../src/voice/audio/mic-tap", () => {
  class MicError extends Error {
    code: string;
    constructor(code: string, message: string) {
      super(message);
      this.code = code;
    }
  }
  const tap = { acquire: async () => undefined, release: () => undefined, onFrame: () => () => undefined, lastVoiceAt: null, active: false, slice: () => null };
  return { MicError, getMicTap: () => tap };
});
vi.mock("../../src/voice/audio/player", () => {
  const player = { attach: () => () => undefined, resume: async () => true, flush, enqueue, playedMs: () => 0, audibleGeneration: null, duck };
  return { getPlayer: () => player };
});
vi.mock("../../src/voice/api", async (orig) => ({
  ...(await orig<typeof import("../../src/voice/api")>()),
  requestRealtimeSession: async () => ({ engine: "openai", model: "test", connect: { url: "wss://x", token: "t" } }),
}));
vi.mock("../../src/voice/analyst", async (orig) => {
  const real = await orig<typeof import("../../src/voice/analyst")>();
  return { ...real, analyze: vi.fn(real.analyze) };
});
// The controller runs the real OpenAI adapter instead of the scripted double.
vi.mock("../../src/voice/engine-factory", async (orig) => {
  const real = await orig<typeof import("../../src/voice/engine-factory")>();
  const { OpenAIRealtimeEngine } = await import("../../src/voice/openai-engine");
  return {
    ...real,
    createEngine: (_id: string, deps: ConstructorParameters<typeof OpenAIRealtimeEngine>[0]) => ({ engine: new OpenAIRealtimeEngine(deps), model: "test", simulated: false }),
  };
});

type Msg = Record<string, unknown>;

class FakeSocket {
  static readonly OPEN = 1;
  static last: FakeSocket | null = null;
  readyState = 1;
  binaryType = "";
  sent: Msg[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.last = this;
    queueMicrotask(() => this.onopen?.({}));
  }
  send(data: string): void {
    this.sent.push(JSON.parse(data) as Msg);
  }
  close(): void {
    this.readyState = 3;
  }
  push(msg: Msg): void {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  sentOfType(type: string): Msg[] {
    return this.sent.filter((m) => m.type === type);
  }
}
vi.stubGlobal("WebSocket", FakeSocket);

const controller = await import("../../src/voice/controller");
const store = await import("../../src/voice/store");
const { analyze } = await import("../../src/voice/analyst");
const { GeminiLiveEngine } = await import("../../src/voice/gemini-engine");
const { MOCK_BRIEF } = await import("../../src/voice/api");
const { TRANSCRIPT_GATE_MS } = await import("../../src/voice/realtime-base");

const pcm = (): string => btoa(String.fromCharCode(...new Uint8Array(960)));
const userBubbles = () => store.getState().utterances.filter((u) => u.role === "user");
const marks = (): string[] => ((globalThis as { __voiceMarks?: { name: string }[] }).__voiceMarks ?? []).map((m) => m.name);

async function openSession(): Promise<FakeSocket> {
  FakeSocket.last = null;
  void controller.start();
  for (let i = 0; i < 100 && !FakeSocket.last?.onmessage; i++) await vi.advanceTimersByTimeAsync(5);
  const ws = FakeSocket.last!;
  ws.push({ type: "session.created", session: { instructions: "base" } });
  await vi.advanceTimersByTimeAsync(50);
  return ws;
}

/** One committed user turn, as the server VAD reports it. */
function userTurn(ws: FakeSocket, item: string): void {
  ws.push({ type: "input_audio_buffer.speech_started", item_id: item, audio_start_ms: 0 });
  ws.push({ type: "input_audio_buffer.speech_stopped", item_id: item, audio_end_ms: 600 });
}

beforeEach(() => {
  vi.useFakeTimers();
  controller.restart();
  enqueue.mockClear();
  duck.mockClear();
  flush.mockClear();
  vi.mocked(analyze).mockClear();
  (globalThis as { __voiceMarks?: unknown[] }).__voiceMarks = [];
});

afterEach(() => {
  controller.restart();
  vi.useRealTimers();
});

describe("noise transcribed as text (OpenAI, through the controller)", () => {
  it("a garbage final transcript shows no bubble, cancels its answer, plays nothing and is not analysed", async () => {
    const ws = await openSession();
    userTurn(ws, "item-1");
    ws.push({ type: "response.created", response: { id: "resp-1" } });
    ws.push({ type: "response.output_audio.delta", response_id: "resp-1", item_id: "a-1", delta: pcm() });
    ws.push({ type: "response.output_audio_transcript.delta", response_id: "resp-1", delta: "La princesa…" });
    ws.push({ type: "conversation.item.input_audio_transcription.delta", item_id: "item-1", delta: "公主" });
    expect(userBubbles()).toHaveLength(0); // the partial never flashes on screen
    ws.push({ type: "conversation.item.input_audio_transcription.completed", item_id: "item-1", transcript: "公主。" });
    await vi.advanceTimersByTimeAsync(3000);

    expect(ws.sentOfType("response.cancel")).toHaveLength(1);
    expect(ws.sentOfType("conversation.item.delete")).toEqual([{ type: "conversation.item.delete", item_id: "item-1" }]);
    expect(enqueue).not.toHaveBeenCalled();
    expect(userBubbles()).toHaveLength(0);
    expect(store.getState().utterances.some((u) => u.role === "agent")).toBe(false);
    expect(analyze).not.toHaveBeenCalled();
    expect(marks()).toContain("asr_garbage_dropped");
    // Anything that still arrives for that answer is dropped.
    ws.push({ type: "response.output_audio.delta", response_id: "resp-1", item_id: "a-1", delta: pcm() });
    ws.push({ type: "response.done", response: { id: "resp-1", status: "cancelled" } });
    expect(enqueue).not.toHaveBeenCalled();
  });

  it("the provider's answer that starts after the garbage transcript is cancelled too", async () => {
    const ws = await openSession();
    userTurn(ws, "item-2");
    ws.push({ type: "conversation.item.input_audio_transcription.completed", item_id: "item-2", transcript: "Gracias por ver el video." });
    ws.push({ type: "response.created", response: { id: "resp-2" } });
    ws.push({ type: "response.output_audio.delta", response_id: "resp-2", item_id: "a-2", delta: pcm() });
    await vi.advanceTimersByTimeAsync(3000);
    expect(ws.sentOfType("response.cancel")).toHaveLength(1);
    expect(enqueue).not.toHaveBeenCalled();
    expect(userBubbles()).toHaveLength(0);
    expect(analyze).not.toHaveBeenCalled();
  });

  it("a partial bubble that ends as a hallucination is removed", async () => {
    const ws = await openSession();
    userTurn(ws, "item-3");
    ws.push({ type: "conversation.item.input_audio_transcription.delta", item_id: "item-3", delta: "Gracias" });
    expect(userBubbles().map((u) => u.text)).toEqual(["Gracias"]);
    ws.push({ type: "conversation.item.input_audio_transcription.completed", item_id: "item-3", transcript: "Gracias." });
    expect(userBubbles()).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(3000);
    expect(analyze).not.toHaveBeenCalled();
  });

  it("a real question is answered: its held audio plays as soon as the transcript confirms it", async () => {
    const ws = await openSession();
    userTurn(ws, "item-4");
    ws.push({ type: "response.created", response: { id: "resp-4" } });
    ws.push({ type: "response.output_audio.delta", response_id: "resp-4", item_id: "a-4", delta: pcm() });
    expect(enqueue).not.toHaveBeenCalled();
    ws.push({ type: "conversation.item.input_audio_transcription.completed", item_id: "item-4", transcript: "¿Cuántas IPS hay en Cali?" });
    expect(enqueue).toHaveBeenCalledWith("resp-4", expect.any(Int16Array));
    expect(ws.sentOfType("response.cancel")).toHaveLength(0);
    expect(userBubbles().map((u) => [u.text, u.final])).toEqual([["¿Cuántas IPS hay en Cali?", true]]);
    await vi.advanceTimersByTimeAsync(3000);
    expect(analyze).toHaveBeenCalledTimes(1);
  });

  it("a short real answer («sí») is answered too", async () => {
    const ws = await openSession();
    userTurn(ws, "item-5");
    ws.push({ type: "conversation.item.input_audio_transcription.completed", item_id: "item-5", transcript: "Sí." });
    ws.push({ type: "response.created", response: { id: "resp-5" } });
    ws.push({ type: "response.output_audio.delta", response_id: "resp-5", item_id: "a-5", delta: pcm() });
    expect(enqueue).toHaveBeenCalledWith("resp-5", expect.any(Int16Array));
    expect(userBubbles().map((u) => u.text)).toEqual(["Sí."]);
    expect(ws.sentOfType("response.cancel")).toHaveLength(0);
  });

  it("a slow transcript never blocks the answer for more than the gate", async () => {
    const ws = await openSession();
    userTurn(ws, "item-6");
    ws.push({ type: "response.created", response: { id: "resp-6" } });
    ws.push({ type: "response.output_audio.delta", response_id: "resp-6", item_id: "a-6", delta: pcm() });
    expect(enqueue).not.toHaveBeenCalledWith("resp-6", expect.any(Int16Array));
    await vi.advanceTimersByTimeAsync(TRANSCRIPT_GATE_MS + 10);
    expect(enqueue).toHaveBeenCalledWith("resp-6", expect.any(Int16Array));
  });

  it("noise while the agent speaks: the agent goes on at full volume, the garbage is not answered", async () => {
    const ws = await openSession();
    ws.push({ type: "response.created", response: { id: "resp-0" } });
    ws.push({ type: "response.output_audio.delta", response_id: "resp-0", item_id: "a-0", delta: pcm() });
    expect(enqueue).toHaveBeenCalledWith("resp-0", expect.any(Int16Array));
    ws.push({ type: "input_audio_buffer.speech_started", item_id: "item-7", audio_start_ms: 0 });
    expect(duck).toHaveBeenLastCalledWith(0.3);
    await vi.advanceTimersByTimeAsync(400);
    ws.push({ type: "input_audio_buffer.speech_stopped", item_id: "item-7", audio_end_ms: 400 });
    expect(duck).toHaveBeenLastCalledWith(1);
    ws.push({ type: "response.created", response: { id: "resp-7" } });
    ws.push({ type: "response.output_audio.delta", response_id: "resp-7", item_id: "a-7", delta: pcm() });
    // Five words used to pass the noise rule; the plausibility filter now drops it.
    ws.push({ type: "conversation.item.input_audio_transcription.completed", item_id: "item-7", transcript: "Gracias por ver el video." });
    await vi.advanceTimersByTimeAsync(3000);
    expect(flush).not.toHaveBeenCalled();
    expect(ws.sentOfType("response.cancel")).toHaveLength(1);
    expect(enqueue).not.toHaveBeenCalledWith("resp-7", expect.any(Int16Array));
    expect(userBubbles()).toHaveLength(0);
    expect(analyze).not.toHaveBeenCalled();
  });
});

describe("noise transcribed as text (Gemini)", () => {
  it("the output of the phantom turn is discarded and nothing of it is shown", async () => {
    const t0 = Date.now();
    const engine = new GeminiLiveEngine({
      now: () => Date.now() - t0,
      getBrief: async () => ({ ...MOCK_BRIEF, spoken_brief: "" }),
      runTool: async () => {
        throw new Error("not used");
      },
      micAllowed: () => false,
    });
    const transcripts: { role: string; text: string; final: boolean }[] = [];
    engine.on("transcript", (ev) => transcripts.push(ev.payload));
    FakeSocket.last = null;
    const connected = engine.connect({ conversationId: "g1" });
    for (let i = 0; i < 100 && !FakeSocket.last?.onmessage; i++) await vi.advanceTimersByTimeAsync(5);
    FakeSocket.last!.push({ setupComplete: {} });
    await connected;
    const ws = FakeSocket.last!;

    ws.push({ voiceActivity: { type: "ACTIVITY_START" } });
    ws.push({ serverContent: { inputTranscription: { text: "公主" } } });
    ws.push({ voiceActivity: { type: "ACTIVITY_END" } });
    ws.push({ serverContent: { modelTurn: { parts: [{ inlineData: { data: pcm() } }] }, outputTranscription: { text: "La princesa" } } });
    await vi.advanceTimersByTimeAsync(400); // the utterance closes with its transcript
    ws.push({ serverContent: { modelTurn: { parts: [{ inlineData: { data: pcm() } }] }, outputTranscription: { text: " dice…" } } });
    ws.push({ serverContent: { turnComplete: true } });
    await vi.advanceTimersByTimeAsync(2000);

    expect(enqueue).not.toHaveBeenCalled();
    expect(transcripts).toEqual([]);
    expect(marks()).toContain("asr_garbage_dropped");
    await engine.disconnect();
  });
});
