/**
 * PcmPlayer: the one playback path for every engine (docs/08 §4).
 *
 * PCM16 mono at 24 kHz is scheduled on a timeline of AudioBufferSourceNodes.
 * At most ~2 s are scheduled ahead; anything beyond waits in a pending list, so
 * `flush()` stops the sound at once even when the provider streamed faster than
 * real time. Played time is tracked per generation (docs/08 §6), and an
 * AnalyserNode sits on the output for the avatar's lip-sync.
 */

const SAMPLE_RATE = 24_000;
/** Scheduling horizon (docs/08 §4: "máximo 2 s en cola"). */
const MAX_AHEAD_S = 2;
/** Safety lead when starting from silence, so the first buffer is not clipped. */
const START_LEAD_S = 0.04;
const TICK_MS = 25;

let sharedContext: AudioContext | null = null;

/** One AudioContext for capture and playback. Create it after a user gesture. */
export function sharedAudioContext(): AudioContext {
  if (!sharedContext || sharedContext.state === "closed") {
    sharedContext = new AudioContext({ latencyHint: "interactive" });
  }
  return sharedContext;
}

export interface PlayerHandlers {
  /** The first sample of a generation is now audible. */
  onGenerationStart?(generationId: string): void;
  /** Nothing of this generation is scheduled or pending any more. */
  onGenerationEnd?(generationId: string): void;
}

interface Scheduled {
  generationId: string;
  source: AudioBufferSourceNode;
  start: number;
  end: number;
}

interface Pending {
  generationId: string;
  samples: Float32Array<ArrayBuffer>;
}

export class PcmPlayer {
  readonly context: AudioContext;
  /** Tap for lip-sync: carries exactly what is being played. */
  readonly analyser: AnalyserNode;
  private readonly output: GainNode;
  private scheduled: Scheduled[] = [];
  private pending: Pending[] = [];
  private nextTime = 0;
  private timer: ReturnType<typeof setInterval> | undefined;
  private handlers: PlayerHandlers | null = null;
  /** ms fully played per generation (finished buffers only). */
  private readonly finished = new Map<string, number>();
  private audible: string | null = null;
  /** Generations whose start was reported and whose end is still owed. */
  private readonly started = new Set<string>();

  constructor(context: AudioContext = sharedAudioContext()) {
    this.context = context;
    this.output = context.createGain();
    this.analyser = context.createAnalyser();
    this.analyser.fftSize = 1024;
    this.analyser.smoothingTimeConstant = 0.5;
    this.output.connect(this.analyser);
    this.analyser.connect(context.destination);
  }

  /** Must run inside (or after) a user gesture: autoplay policy (docs/08 §4). */
  async resume(): Promise<boolean> {
    if (this.context.state !== "running") {
      try {
        await this.context.resume();
      } catch {
        return false;
      }
    }
    return this.context.state === "running";
  }

  /** The current owner receives the callbacks; the returned function releases them. */
  attach(handlers: PlayerHandlers): () => void {
    this.handlers = handlers;
    return () => {
      if (this.handlers === handlers) this.handlers = null;
    };
  }

  /**
   * Queues PCM16 mono 24 kHz. Returns the delay in ms until its first sample is
   * audible (an estimate when the chunk has to wait behind the 2 s horizon).
   */
  enqueue(generationId: string, pcm: Int16Array): number {
    if (pcm.length === 0) return this.queuedMs();
    const samples = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) samples[i] = (pcm[i] ?? 0) / 32768;
    const delayMs = this.playing ? this.queuedMs() : START_LEAD_S * 1000;
    this.pending.push({ generationId, samples });
    this.pump();
    this.ensureTimer();
    return delayMs;
  }

  /** ms of audio not yet played (scheduled + pending). */
  queuedMs(): number {
    const now = this.context.currentTime;
    let ms = Math.max(0, this.nextTime - now) * 1000;
    for (const p of this.pending) ms += (p.samples.length / SAMPLE_RATE) * 1000;
    return ms;
  }

  get playing(): boolean {
    return this.scheduled.length > 0 || this.pending.length > 0;
  }

  /** Generation whose samples are audible right now, if any. */
  get audibleGeneration(): string | null {
    return this.audible;
  }

  /** ms of this generation that actually left the speakers. */
  playedMs(generationId: string): number {
    const now = this.context.currentTime;
    let ms = this.finished.get(generationId) ?? 0;
    for (const s of this.scheduled) {
      if (s.generationId !== generationId) continue;
      ms += Math.max(0, Math.min(now, s.end) - s.start) * 1000;
    }
    return Math.round(ms);
  }

  /**
   * Stops the sound immediately and empties the queue (docs/08 §6.2). Returns
   * the played ms of every generation that still had audio queued.
   */
  flush(): Map<string, number> {
    const cut = new Map<string, number>();
    for (const s of this.scheduled) cut.set(s.generationId, 0);
    for (const p of this.pending) cut.set(p.generationId, 0);
    for (const id of cut.keys()) cut.set(id, this.playedMs(id));
    for (const s of this.scheduled) {
      s.source.onended = null;
      try {
        s.source.stop();
      } catch {
        // already stopped
      }
      s.source.disconnect();
    }
    for (const [id, ms] of cut) this.finished.set(id, ms);
    this.scheduled = [];
    this.pending = [];
    this.nextTime = 0;
    this.audible = null;
    this.started.clear();
    this.stopTimer();
    return cut;
  }

  // ── Scheduling ─────────────────────────────────────────────────────────────

  private pump(): void {
    const ctx = this.context;
    while (this.pending.length > 0) {
      const now = ctx.currentTime;
      const ahead = Math.max(0, this.nextTime - now);
      const next = this.pending[0];
      if (!next) break;
      const duration = next.samples.length / SAMPLE_RATE;
      if (ahead > 0 && ahead + duration > MAX_AHEAD_S) break;
      this.pending.shift();
      const buffer = ctx.createBuffer(1, next.samples.length, SAMPLE_RATE);
      buffer.copyToChannel(next.samples, 0);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(this.output);
      const start = Math.max(this.nextTime, now + START_LEAD_S);
      const entry: Scheduled = { generationId: next.generationId, source, start, end: start + duration };
      source.onended = () => this.onEnded(entry);
      source.start(start);
      this.scheduled.push(entry);
      this.nextTime = entry.end;
    }
  }

  private onEnded(entry: Scheduled): void {
    const i = this.scheduled.indexOf(entry);
    if (i < 0) return;
    this.scheduled.splice(i, 1);
    entry.source.disconnect();
    this.finished.set(entry.generationId, (this.finished.get(entry.generationId) ?? 0) + (entry.end - entry.start) * 1000);
    if (this.finished.size > 16) {
      const oldest = this.finished.keys().next().value;
      if (oldest !== undefined && oldest !== entry.generationId) this.finished.delete(oldest);
    }
    // A buffer shorter than one tick may never have been seen as audible.
    this.noteStart(entry.generationId);
    this.tick();
  }

  private noteStart(generationId: string): void {
    if (this.started.has(generationId)) return;
    this.started.add(generationId);
    this.handlers?.onGenerationStart?.(generationId);
  }

  /** Tells the owner which generation became audible and which ones ran out of audio. */
  private tick(): void {
    this.pump();
    const now = this.context.currentTime;
    const current = this.scheduled.find((s) => s.start <= now && now < s.end)?.generationId ?? null;
    this.audible = current;
    if (current !== null) this.noteStart(current);
    for (const id of [...this.started]) {
      const queued = this.scheduled.some((s) => s.generationId === id) || this.pending.some((p) => p.generationId === id);
      if (queued) continue;
      this.started.delete(id);
      this.handlers?.onGenerationEnd?.(id);
    }
    if (!this.playing) this.stopTimer();
  }

  private ensureTimer(): void {
    this.timer ??= setInterval(() => this.tick(), TICK_MS);
  }

  private stopTimer(): void {
    clearInterval(this.timer);
    this.timer = undefined;
  }
}

let sharedPlayer: PcmPlayer | null = null;

/** The single player of the page; the avatar reads its analyser. */
export function getPlayer(): PcmPlayer {
  if (!sharedPlayer || sharedPlayer.context.state === "closed") sharedPlayer = new PcmPlayer();
  return sharedPlayer;
}
