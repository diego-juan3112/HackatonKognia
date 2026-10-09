/**
 * Cartesia adapter of the client-side SpeechSynthesizer port (docs/08 §15.2).
 *
 * The engine writes text only; this adapter turns it into PCM16 mono 24 kHz, the
 * format of the shared PcmPlayer. One provider context per generation: every
 * sentence is sent with `continue: true` and the context is closed with an empty
 * `continue: false` message. Provider message names, the context id, base64, the
 * URL and the access token never leave this file (R-03); the token lives in
 * memory only and the team key never reaches the browser (R-28).
 */
import { apiFetch } from "./api";

export interface SynthWord {
  text: string;
  start_ms: number;
  end_ms: number;
}

export interface SynthEvents {
  /** PCM16 mono 24 kHz. */
  audio: { generation_id: string; pcm: Int16Array };
  words: { generation_id: string; words: SynthWord[] };
  done: { generation_id: string };
  error: { code: "SYNTH_CONNECT_FAILED" | "SYNTH_DROPPED" | "SYNTH_QUOTA"; retryable: boolean };
}

export interface SpeechSynthesizer {
  /** Only for the HUD. */
  readonly id: string;
  /** Asks for the credential, opens the connection and keeps it warm. */
  connect(): Promise<void>;
  /** Whole sentences, in order. `final` closes the generation. */
  speak(generationId: string, text: string, opts: { final: boolean }): void;
  /** Stops asking for audio and drops whatever arrives late. */
  cancel(generationId: string): void;
  disconnect(): Promise<void>;
  on<K extends keyof SynthEvents>(e: K, cb: (ev: SynthEvents[K]) => void): () => void;
}

interface SpeechGrant {
  model: string;
  connect: { url: string; token: string };
  config: { voice_id: string; language?: string; timestamps?: boolean };
}

interface Context {
  generationId: string;
  closed: boolean;
  /** Odd byte left over from a chunk that split a sample. */
  carry: number | null;
  timer: ReturnType<typeof setTimeout> | undefined;
}

/** `/speech/session` fails or the socket does not open in this time → engine voice (docs/08 §15.6). */
const CONNECT_TIMEOUT_MS = 6000;
/** Silence from the provider while audio is owed → synthesizer failure (docs/08 §15.5). */
const STALL_TIMEOUT_MS = 4000;

type Listeners = { [K in keyof SynthEvents]?: Set<(ev: SynthEvents[K]) => void> };

export class CartesiaSynthesizer implements SpeechSynthesizer {
  readonly id = "cartesia";
  private readonly conversationId: string;
  private readonly listeners: Listeners = {};
  private ws: WebSocket | null = null;
  private grant: SpeechGrant | null = null;
  private opening: Promise<void> | null = null;
  private closedByUs = false;
  /** Provider context id → state. One context per generation. */
  private readonly contexts = new Map<string, Context>();
  private readonly cancelled = new Set<string>();
  /** Messages waiting for a reconnection. */
  private outbox: string[] = [];

  constructor(conversationId: string) {
    this.conversationId = conversationId;
  }

  on<K extends keyof SynthEvents>(e: K, cb: (ev: SynthEvents[K]) => void): () => void {
    const set = (this.listeners[e] ??= new Set() as never) as Set<(ev: SynthEvents[K]) => void>;
    set.add(cb);
    return () => set.delete(cb);
  }

  private emit<K extends keyof SynthEvents>(e: K, ev: SynthEvents[K]): void {
    (this.listeners[e] as Set<(ev: SynthEvents[K]) => void> | undefined)?.forEach((cb) => cb(ev));
  }

  connect(): Promise<void> {
    this.closedByUs = false;
    return this.open();
  }

  private open(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) return Promise.resolve();
    this.opening ??= this.doOpen().finally(() => {
      this.opening = null;
    });
    return this.opening;
  }

  private async doOpen(): Promise<void> {
    const deadline = performance.now() + CONNECT_TIMEOUT_MS;
    const res = await apiFetch("/speech/session", { method: "POST", body: JSON.stringify({ conversation_id: this.conversationId }) }, CONNECT_TIMEOUT_MS);
    if (!res.ok) throw new SynthError(res.status === 429 ? "SYNTH_QUOTA" : "SYNTH_CONNECT_FAILED");
    const grant = (await res.json()) as SpeechGrant;
    if (!grant.connect?.url || !grant.connect.token || !grant.config?.voice_id) throw new SynthError("SYNTH_CONNECT_FAILED");
    this.grant = grant;
    // A browser cannot set headers on a WebSocket: the provider takes the token in the URL.
    const url = grant.connect.url.includes("access_token=")
      ? grant.connect.url
      : `${grant.connect.url}${grant.connect.url.includes("?") ? "&" : "?"}access_token=${encodeURIComponent(grant.connect.token)}`;
    const ws = await new Promise<WebSocket>((resolve, reject) => {
      let socket: WebSocket;
      try {
        socket = new WebSocket(url);
      } catch {
        reject(new SynthError("SYNTH_CONNECT_FAILED"));
        return;
      }
      const timer = setTimeout(() => {
        socket.onopen = socket.onerror = socket.onclose = null;
        try {
          socket.close();
        } catch {
          // ignore
        }
        reject(new SynthError("SYNTH_CONNECT_FAILED"));
      }, Math.max(500, deadline - performance.now()));
      socket.onopen = () => {
        clearTimeout(timer);
        resolve(socket);
      };
      socket.onerror = socket.onclose = () => {
        clearTimeout(timer);
        reject(new SynthError("SYNTH_CONNECT_FAILED"));
      };
    });
    if (this.closedByUs) {
      ws.close();
      throw new SynthError("SYNTH_CONNECT_FAILED");
    }
    this.ws = ws;
    ws.onerror = null;
    ws.onmessage = (ev) => this.onMessage(ev.data);
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      // Idle closes are normal: the next sentence reconnects. A close with audio owed is a failure.
      const owed = [...this.contexts.values()].some((c) => !c.closed || c.timer !== undefined);
      if (!this.closedByUs && owed) this.failAll("SYNTH_DROPPED", true);
    };
    const queued = this.outbox;
    this.outbox = [];
    for (const m of queued) ws.send(m);
  }

  speak(generationId: string, text: string, opts: { final: boolean }): void {
    if (this.cancelled.has(generationId) || this.closedByUs) return;
    let ctx = this.contexts.get(generationId);
    if (!ctx) {
      if (!text.trim()) return; // nothing was ever said in this generation
      ctx = { generationId, closed: false, carry: null, timer: undefined };
      this.contexts.set(generationId, ctx);
    }
    if (ctx.closed) return;
    if (text.trim()) this.sendFor(generationId, text, true);
    if (opts.final) {
      ctx.closed = true;
      this.sendFor(generationId, "", false);
    }
    this.arm(ctx);
  }

  private sendFor(contextId: string, transcript: string, more: boolean): void {
    const grant = this.grant;
    if (!grant) return;
    const msg = JSON.stringify({
      model_id: grant.model,
      transcript,
      voice: { mode: "id", id: grant.config.voice_id },
      language: grant.config.language ?? "es",
      context_id: contextId,
      continue: more,
      output_format: { container: "raw", encoding: "pcm_s16le", sample_rate: 24_000 },
      add_timestamps: grant.config.timestamps !== false,
    });
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(msg);
      return;
    }
    // The connection idled out between turns: one reconnection attempt (docs/08 §15.6).
    this.outbox.push(msg);
    this.open().catch((err: unknown) => {
      this.outbox = [];
      this.failAll(err instanceof SynthError ? err.code : "SYNTH_CONNECT_FAILED", false);
    });
  }

  cancel(generationId: string): void {
    const ctx = this.contexts.get(generationId);
    this.cancelled.add(generationId);
    if (this.cancelled.size > 32) {
      const oldest = this.cancelled.values().next().value;
      if (oldest !== undefined) this.cancelled.delete(oldest);
    }
    if (!ctx) return;
    clearTimeout(ctx.timer);
    this.contexts.delete(generationId);
    // Only stops what has not started generating; late chunks are dropped on arrival.
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ context_id: generationId, cancel: true }));
  }

  async disconnect(): Promise<void> {
    this.closedByUs = true;
    for (const c of this.contexts.values()) clearTimeout(c.timer);
    this.contexts.clear();
    this.outbox = [];
    this.grant = null;
    const ws = this.ws;
    this.ws = null;
    if (ws) {
      ws.onmessage = ws.onclose = ws.onerror = null;
      try {
        ws.close();
      } catch {
        // already closed
      }
    }
  }

  private arm(ctx: Context): void {
    clearTimeout(ctx.timer);
    ctx.timer = setTimeout(() => {
      ctx.timer = undefined;
      if (this.contexts.get(ctx.generationId) === ctx) this.failAll("SYNTH_DROPPED", true);
    }, STALL_TIMEOUT_MS);
  }

  private failAll(code: SynthEvents["error"]["code"], retryable: boolean): void {
    for (const c of this.contexts.values()) clearTimeout(c.timer);
    this.contexts.clear();
    this.emit("error", { code, retryable });
  }

  private onMessage(data: unknown): void {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(typeof data === "string" ? data : new TextDecoder().decode(data as ArrayBuffer)) as Record<string, unknown>;
    } catch {
      return;
    }
    const contextId = typeof msg.context_id === "string" ? msg.context_id : "";
    const ctx = this.contexts.get(contextId);
    if (msg.type === "error") {
      if (!ctx) return; // an error about a cancelled context is expected
      const text = JSON.stringify(msg).toLowerCase();
      const quota = /quota|credit|limit|concurren|402|429/.test(text);
      console.warn(`[voice:cartesia] synthesis error${typeof msg.status_code === "number" ? ` ${msg.status_code}` : ""}`);
      this.failAll(quota ? "SYNTH_QUOTA" : "SYNTH_DROPPED", !quota);
      return;
    }
    if (!ctx) return; // late message of a cancelled or finished generation
    const generationId = ctx.generationId;
    if (msg.type === "chunk" && typeof msg.data === "string") {
      // While sentences are still coming, silence between them is the engine's, not ours.
      if (ctx.closed) this.arm(ctx);
      else {
        clearTimeout(ctx.timer);
        ctx.timer = undefined;
      }
      const pcm = decode(msg.data, ctx);
      if (pcm.length > 0) this.emit("audio", { generation_id: generationId, pcm });
    } else if (msg.type === "timestamps") {
      const w = (msg.word_timestamps ?? {}) as { words?: unknown; start?: unknown; end?: unknown };
      const texts = Array.isArray(w.words) ? w.words : [];
      const start = Array.isArray(w.start) ? w.start : [];
      const end = Array.isArray(w.end) ? w.end : [];
      const words: SynthWord[] = [];
      for (let i = 0; i < texts.length; i++) {
        const s = Number(start[i]);
        const e = Number(end[i]);
        if (typeof texts[i] === "string" && Number.isFinite(s) && Number.isFinite(e)) words.push({ text: texts[i] as string, start_ms: Math.round(s * 1000), end_ms: Math.round(e * 1000) });
      }
      if (words.length > 0) this.emit("words", { generation_id: generationId, words });
    } else if (msg.type === "done") {
      clearTimeout(ctx.timer);
      this.contexts.delete(contextId);
      this.emit("done", { generation_id: generationId });
    }
  }
}

class SynthError extends Error {
  readonly code: SynthEvents["error"]["code"];
  constructor(code: SynthEvents["error"]["code"]) {
    super(code);
    this.code = code;
  }
}

function decode(base64: string, ctx: Context): Int16Array {
  const binary = atob(base64);
  if (binary.length === 0) return new Int16Array(0);
  const offset = ctx.carry === null ? 0 : 1;
  const total = binary.length + offset;
  const bytes = new Uint8Array(total & ~1);
  if (ctx.carry !== null && bytes.length > 0) bytes[0] = ctx.carry;
  for (let i = offset; i < bytes.length; i++) bytes[i] = binary.charCodeAt(i - offset);
  ctx.carry = total % 2 === 1 ? binary.charCodeAt(binary.length - 1) : null;
  return new Int16Array(bytes.buffer);
}

/**
 * Splits streamed text into whole sentences (docs/08 §15.3). A closing mark only
 * counts when whitespace follows it, so «10.000» or «3:30» are never cut.
 */
export class SentenceChunker {
  private buffer = "";

  push(delta: string): string[] {
    this.buffer += delta;
    const out: string[] = [];
    const re = /[.?!:…]+["»)]?\s+|\n+/g;
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(this.buffer)) !== null) {
      const end = m.index + m[0].length;
      const piece = this.buffer.slice(last, end);
      if (piece.trim()) out.push(piece);
      last = end;
    }
    this.buffer = this.buffer.slice(last);
    return out;
  }

  flush(): string {
    const rest = this.buffer;
    this.buffer = "";
    return rest;
  }
}
