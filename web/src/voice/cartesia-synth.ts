/**
 * Cartesia adapter of the SpeechSynthesizer port (docs/08 §15.2–§15.4): the cloned
 * voice. The engine produces text only; this turns it into PCM16 mono 24 kHz for
 * the same player. Message names, context ids, base64 and the URL/token never
 * leave this file (R-03).
 */
import { apiFetch, ApiError, USING_MOCKS } from "./api";
import { base64ToPcm, openSocket, parseFrame } from "./realtime-base";

export interface SynthWord {
  text: string;
  start_ms: number;
  end_ms: number;
}

export interface SynthEvents {
  audio: { generation_id: string; pcm: Int16Array };
  words: { generation_id: string; words: SynthWord[] };
  done: { generation_id: string };
  error: { code: "SYNTH_CONNECT_FAILED" | "SYNTH_DROPPED" | "SYNTH_QUOTA"; retryable: boolean };
}

export interface SpeechSynthesizer {
  readonly id: string;
  connect(conversationId: string): Promise<void>;
  speak(generationId: string, text: string, opts: { final: boolean }): void;
  cancel(generationId: string): void;
  disconnect(): Promise<void>;
  on<K extends keyof SynthEvents>(e: K, cb: (ev: SynthEvents[K]) => void): () => void;
}

/** The WebSocket must open within this or the session falls back to the engine voice. */
export const SYNTH_OPEN_TIMEOUT_MS = 3000;

interface Grant {
  model: string;
  connect: { url: string; token: string };
  config: { voice_id: string; language?: string; audio?: { sample_rate?: number } };
}

type Msg = Record<string, unknown>;
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const nums = (v: unknown): number[] => (Array.isArray(v) ? v.map((x) => (typeof x === "number" ? x : 0)) : []);

export class CartesiaSynthesizer implements SpeechSynthesizer {
  readonly id = "cartesia";
  private ws: WebSocket | null = null;
  private grant: Grant | null = null;
  private readonly listeners: { [K in keyof SynthEvents]?: Set<(ev: SynthEvents[K]) => void> } = {};
  /** generation id → context id, and back. */
  private readonly contexts = new Map<string, string>();
  private readonly generations = new Map<string, string>();
  private readonly cancelled = new Set<string>();
  /** Debug counters, read by the live smoke test. */
  readonly stats = { chunks: 0, bytes: 0 };

  async connect(conversationId: string): Promise<void> {
    if (USING_MOCKS) throw new ApiError(503, "SYNTH_UNAVAILABLE", "Sin backend no hay voz clonada.");
    const res = await apiFetch("/speech/session", { method: "POST", body: JSON.stringify({ conversation_id: conversationId }) }, SYNTH_OPEN_TIMEOUT_MS);
    if (!res.ok) throw new ApiError(res.status, res.status === 429 ? "SYNTH_QUOTA" : "SYNTH_UNAVAILABLE", `La API respondió ${res.status} al pedir la voz clonada.`);
    const grant = (await res.json()) as Grant;
    if (!grant.connect?.url || !grant.config?.voice_id) throw new ApiError(502, "SYNTH_CONNECT_FAILED", "Credencial de voz clonada incompleta.");
    this.grant = grant;
    const ws = await Promise.race([
      openSocket(grant.connect.url),
      new Promise<never>((_, reject) => setTimeout(() => reject(new Error("synth open timeout")), SYNTH_OPEN_TIMEOUT_MS)),
    ]);
    this.ws = ws;
    ws.onmessage = (ev) => this.onMessage(ev.data);
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.emit("error", { code: "SYNTH_DROPPED", retryable: true });
    };
  }

  get ready(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  speak(generationId: string, text: string, opts: { final: boolean }): void {
    if (!this.ws || !this.grant || this.cancelled.has(generationId)) return;
    let ctx = this.contexts.get(generationId);
    if (!ctx) {
      ctx = crypto.randomUUID();
      this.contexts.set(generationId, ctx);
      this.generations.set(ctx, generationId);
    }
    this.send({
      model_id: this.grant.model,
      transcript: text,
      voice: { mode: "id", id: this.grant.config.voice_id },
      language: this.grant.config.language ?? "es",
      context_id: ctx,
      continue: !opts.final,
      output_format: { container: "raw", encoding: "pcm_s16le", sample_rate: 24000 },
      add_timestamps: true,
    });
  }

  cancel(generationId: string): void {
    this.cancelled.add(generationId);
    const ctx = this.contexts.get(generationId);
    if (ctx) this.send({ context_id: ctx, cancel: true });
  }

  async disconnect(): Promise<void> {
    const ws = this.ws;
    this.ws = null;
    this.contexts.clear();
    this.generations.clear();
    this.cancelled.clear();
    if (!ws) return;
    ws.onmessage = ws.onclose = ws.onerror = null;
    try {
      ws.close();
    } catch {
      // already closed
    }
  }

  on<K extends keyof SynthEvents>(e: K, cb: (ev: SynthEvents[K]) => void): () => void {
    const set = (this.listeners[e] ??= new Set() as never) as Set<(ev: SynthEvents[K]) => void>;
    set.add(cb);
    return () => set.delete(cb);
  }

  private emit<K extends keyof SynthEvents>(e: K, ev: SynthEvents[K]): void {
    (this.listeners[e] as Set<(ev: SynthEvents[K]) => void> | undefined)?.forEach((cb) => cb(ev));
  }

  private send(msg: Msg): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  private onMessage(data: unknown): void {
    const msg = parseFrame(data);
    if (!msg) return;
    const gen = this.generations.get(str(msg.context_id));
    if (!gen || this.cancelled.has(gen)) return; // late output of a cancelled context
    const type = str(msg.type);
    if (type === "chunk" && typeof msg.data === "string" && msg.data) {
      const pcm = base64ToPcm(msg.data);
      this.stats.chunks++;
      this.stats.bytes += pcm.byteLength;
      this.emit("audio", { generation_id: gen, pcm });
    } else if (type === "timestamps") {
      const wt = (msg.word_timestamps ?? {}) as Msg;
      const words = Array.isArray(wt.words) ? wt.words.map(String) : [];
      const start = nums(wt.start);
      const end = nums(wt.end);
      this.emit("words", { generation_id: gen, words: words.map((text, i) => ({ text, start_ms: (start[i] ?? 0) * 1000, end_ms: (end[i] ?? 0) * 1000 })) });
    } else if (type === "done") {
      this.emit("done", { generation_id: gen });
    } else if (type === "error") {
      const quota = /quota|rate|limit|concurren/i.test(`${str(msg.error)} ${str(msg.title)}`);
      console.warn(`[voice:cartesia] ${str(msg.error) || str(msg.title) || "error"}`);
      this.emit("done", { generation_id: gen });
      if (quota) this.emit("error", { code: "SYNTH_QUOTA", retryable: true });
    }
  }
}

/** Splits streamed text into whole sentences (. ? ! : or a line break followed by a space or the end). */
export function takeSentences(buffer: string, final: boolean): { ready: string[]; rest: string } {
  const ready: string[] = [];
  const re = /[.?!:\n](?=\s|$)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(buffer))) {
    // A full stop at the very end of a partial buffer may still grow (e.g. "9." of "9.320").
    if (!final && m.index === buffer.length - 1 && buffer[m.index] === ".") break;
    const s = buffer.slice(last, m.index + 1).trim();
    if (s) ready.push(s);
    last = m.index + 1;
  }
  let rest = buffer.slice(last);
  if (final && rest.trim()) {
    ready.push(rest.trim());
    rest = "";
  }
  return { ready, rest };
}
