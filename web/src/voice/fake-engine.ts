/**
 * FakeEngine: a scripted VoiceEngine double (docs/08 §13).
 *
 * It speaks no audio and opens no socket. It emits the same events a real
 * adapter would, on realistic timings, so the whole console can be built,
 * demoed and tested without credentials or a microphone.
 *
 * Script: brief → question with partials → `aggregate_ips` → answer →
 * follow-up → the user barges in → «No, dije Melgar» → `correct_context` →
 * new query → the engine drops (so the controller switches engines).
 *
 * Every figure the agent "says" comes from the evidence envelope returned by
 * the injected tool executor, never from a literal in this file.
 */
import type { ToolContext } from "./api";
import type {
  ContextEnvelope,
  DatasetBrief,
  EngineEvent,
  EngineEvents,
  EngineId,
  EvidenceEnvelope,
  LatencyPayload,
  SpeechKind,
  StyleDecision,
  ToolCallPayload,
  ToolName,
  VoiceEngine,
  VoiceMode,
} from "./types";

/** What an adapter needs from the UI: the tool bridge and the brief (docs/08 §5). */
export interface EngineDeps {
  runTool(call: ToolCallPayload, ctx: ToolContext): Promise<EvidenceEnvelope>;
  getBrief(): Promise<DatasetBrief>;
  /** Session clock in ms; it keeps running across an engine switch (docs/08 §2, `t`). */
  now(): number;
}

export interface FakeEngineOptions {
  /** Play the scripted user turns after the brief. */
  script?: boolean;
  /** After the script, emit ENGINE_DROPPED so the controller exercises the switch (A-23). */
  dropAtEnd?: boolean;
}

interface Reply {
  ack?: string;
  tool?: { name: ToolName; args: Record<string, unknown> };
  /** Builds the spoken answer from validated evidence (R-22). */
  say(env: EvidenceEnvelope | null, concise: boolean): string;
  interruptAfterWords?: number;
}

const WORD_MS = 165; // simulated playback pace
const TEXT_LEAD_WORDS = 7; // text arrives ahead of the audio, as with real providers
const PARTIAL_MS = 120;
const ACK = "Déjame verificarlo en datos.gov.co.";
const SOURCE = "según el REPS, con corte a noviembre de 2022";
const NO_FIGURE = "No pude consultar la fuente en este momento y no voy a darte una cifra sin verificarla. ¿Lo intento de nuevo?";

const nf = new Intl.NumberFormat("es-CO");
const fmt = (n: unknown): string => (typeof n === "number" ? nf.format(n) : "un valor no registrado");

const fold = (s: string): string =>
  s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

const titleCase = (s: string): string => s.toLowerCase().replace(/(^|\s)\p{L}/gu, (m) => m.toUpperCase());

const ok = (env: EvidenceEnvelope | null): env is EvidenceEnvelope => env !== null && env.status === "ok" && env.data !== null;

class Cancelled extends Error {}

// ── Replies ──────────────────────────────────────────────────────────────────

const bedsIn = (municipality: string, label: string): Reply => ({
  ack: ACK,
  tool: { name: "aggregate_ips", args: { metric: "capacity_sum", filters: { capacity_group: "CAMAS", municipality } } },
  say: (env, concise) =>
    !ok(env)
      ? NO_FIGURE
      : concise
        ? `${fmt(env.data?.value)} camas instaladas en ${label}. Corte REPS: noviembre de 2022.`
        : `En ${label} hay ${fmt(env.data?.value)} camas instaladas, ${SOURCE}. Es capacidad instalada, no disponibilidad de hoy. Si quieres, también puedo contarte cuántas IPS hay en ese municipio o compararlo con otro.`,
});

const REPLIES = {
  topBeds: {
    ack: ACK,
    tool: {
      name: "aggregate_ips",
      args: { metric: "capacity_sum", filters: { capacity_group: "CAMAS" }, group_by: "municipality", order: "desc", top_n: 3 },
    },
    say: (env, concise) => {
      if (!ok(env) || !env.data?.groups) return NO_FIGURE;
      const parts = env.data.groups.map((g) => `${titleCase(String(g.key).split(" · ")[0] ?? "")} con ${fmt(g.value)}`);
      const list = `${parts.slice(0, -1).join(", ")} y ${parts[parts.length - 1]}`;
      return concise
        ? `${list}. Corte REPS: noviembre de 2022.`
        : `Los municipios con más camas instaladas son ${list}, ${SOURCE}. Son camas instaladas de todos los tipos, no camas disponibles hoy.`;
    },
  },
  byNature: {
    ack: ACK,
    tool: { name: "aggregate_ips", args: { metric: "provider_count", filters: {}, group_by: "nature" } },
    say: (env, concise) => {
      if (!ok(env) || !env.data?.groups) return NO_FIGURE;
      const g = env.data.groups;
      const total = g.reduce((sum, x) => sum + x.value, 0);
      const list = g.map((x) => `${fmt(x.value)} de naturaleza ${String(x.key).toLowerCase()}`).join(", ");
      return concise ? `${list}. Corte REPS: noviembre de 2022.` : `Hay ${fmt(total)} prestadores: ${list}, ${SOURCE}.`;
    },
  },
  providersTotal: {
    ack: ACK,
    tool: { name: "aggregate_ips", args: { metric: "provider_count", filters: {} } },
    say: (env, concise) =>
      !ok(env)
        ? NO_FIGURE
        : concise
          ? `${fmt(env.data?.value)} prestadores distintos. Corte REPS: noviembre de 2022.`
          : `Hay ${fmt(env.data?.value)} prestadores distintos, ${SOURCE}. Cuento prestadores, no filas: cada fila de la fuente es una categoría de capacidad de una sede.`,
  },
  providersBogota: {
    ack: ACK,
    tool: { name: "aggregate_ips", args: { metric: "provider_count", filters: { department: "Bogotá D.C" } } },
    say: (env, concise) =>
      !ok(env)
        ? NO_FIGURE
        : concise
          ? `${fmt(env.data?.value)} prestadores en Bogotá. Corte REPS: noviembre de 2022.`
          : `En Bogotá hay ${fmt(env.data?.value)} prestadores distintos, ${SOURCE}.`,
  },
  bedsTotal: {
    ack: ACK,
    tool: { name: "aggregate_ips", args: { metric: "capacity_sum", filters: { capacity_group: "CAMAS" } } },
    say: (env, concise) =>
      !ok(env)
        ? NO_FIGURE
        : concise
          ? `${fmt(env.data?.value)} camas instaladas en total. Corte REPS: noviembre de 2022.`
          : `En todo el país hay ${fmt(env.data?.value)} camas instaladas, sumando todos los tipos de cama, ${SOURCE}. Es capacidad instalada, no disponibilidad.`,
  },
  unsupported: {
    say: (_env, concise) =>
      concise
        ? "La fuente no tiene disponibilidad ni ubicación. Sí puedo darte las camas instaladas de un municipio."
        : "Eso no lo puedo saber: la fuente registra capacidad instalada con corte a noviembre de 2022 y no tiene disponibilidad en tiempo real ni geolocalización. Sí puedo decirte cuántas camas instaladas o cuántas IPS hay en un municipio.",
  },
  uncovered: {
    say: () =>
      "Este es el motor simulado y su guion no cubre ese lugar, así que no voy a darte una cifra que no consulté. Con un motor real se consultaría en datos.gov.co.",
  },
  direct: { say: () => "Entendido. Desde ahora respondo más breve y con la cifra primero." },
  thanks: { say: () => "Con gusto. ¿Qué más quieres consultar?" },
  offScript: {
    say: () =>
      "Este es el motor simulado y solo responde las preguntas del guion: prueba con una de las sugeridas. Con un motor real, esta pregunta se consultaría en datos.gov.co.",
  },
} satisfies Record<string, Reply>;

function pickReply(text: string): Reply {
  const q = fold(text);
  if (/disponib|hoy|cercan|cerca /.test(q)) return REPLIES.unsupported;
  if (/camas/.test(q)) {
    if (/melgar/.test(q)) return bedsIn("MELGAR", "Melgar, Tolima");
    if (/medellin/.test(q)) return bedsIn("MEDELLÍN", "Medellín");
    if (/municipio/.test(q)) return REPLIES.topBeds;
    if (/total|pais|colombia|cuantas camas hay\??$/.test(q)) return REPLIES.bedsTotal;
    return REPLIES.offScript;
  }
  if (/publicas|privadas|mixtas|naturaleza/.test(q)) return REPLIES.byNature;
  if (/(ips|prestadores)/.test(q) && /bogota/.test(q)) return REPLIES.providersBogota;
  // A place the script does not cover must never be answered with the national total.
  if (/(ips|prestadores)/.test(q) && /\ben (?!total\b|el pais\b|todo\b|colombia\b)[a-z]/.test(q)) return REPLIES.uncovered;
  if (/cuant\w+ (ips|prestadores)/.test(q)) return REPLIES.providersTotal;
  if (/directo|confund|breve/.test(q)) return REPLIES.direct;
  if (/gracias/.test(q)) return REPLIES.thanks;
  return REPLIES.offScript;
}

// ── Engine ───────────────────────────────────────────────────────────────────

type Listeners = { [K in keyof EngineEvents]?: Set<(ev: EngineEvent<K>) => void> };

interface Speaking {
  generationId: string;
  utteranceId: string;
  words: string[];
  heard: number;
  shown: number;
  tStart: number;
  kind: SpeechKind;
}

export class FakeEngine implements VoiceEngine {
  readonly id: EngineId;
  private readonly deps: EngineDeps;
  private readonly opts: FakeEngineOptions;
  private readonly listeners: Listeners = {};
  private seq = 0;
  private conversationId = "";
  private turnId: string | null = null;
  private stateVersion = 1;
  private generationId: string | null = null;
  private run = 0;
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private speaking: Speaking | null = null;
  private style: StyleDecision | undefined;
  private lastAnswer: string | null = null;
  private latency: LatencyPayload | null = null;
  private connected = false;

  constructor(id: EngineId, deps: EngineDeps, opts: FakeEngineOptions = {}) {
    this.id = id;
    this.deps = deps;
    this.opts = opts;
  }

  // ── VoiceEngine ────────────────────────────────────────────────────────────

  async connect(opts: { conversationId: string; seed?: ContextEnvelope; style?: StyleDecision; voiceMode?: VoiceMode }): Promise<void> {
    this.conversationId = opts.conversationId;
    this.style = opts.style;
    this.connected = true;
    const run = ++this.run;
    if (opts.seed) {
      // Resuming: the context envelope replaces the greeting. Nothing already said is replayed.
      this.seed(opts.seed);
      this.emit("status", { state: "renewing" });
      await this.sleep(900, run);
      this.emit("status", { state: "listening" });
      return;
    }
    this.emit("status", { state: "connecting" });
    const [brief] = await Promise.all([this.deps.getBrief(), this.sleep(650, run)]);
    this.launch(async (r) => {
      await this.speak(brief.spoken_brief, "brief", r);
      this.emit("status", { state: "listening" });
      if (this.opts.script) await this.playScript(r);
    }, run);
  }

  async disconnect(_reason?: string): Promise<void> {
    this.cancel();
    this.connected = false;
    this.speaking = null;
  }

  sendText(text: string): void {
    if (!this.connected) return;
    if (this.speaking) this.cutSpeech(this.playedMs());
    this.cancel();
    this.launch((r) => this.textTurn(text, r), this.run);
  }

  interrupt(playedMs: number, _deliveredText?: string): void {
    if (!this.speaking) return;
    this.cutSpeech(playedMs > 0 ? playedMs : this.playedMs());
    this.cancel();
    this.emit("status", { state: "listening" });
  }

  applyStyle(style: StyleDecision): void {
    this.style = style;
  }

  seed(context: ContextEnvelope): void {
    this.stateVersion = context.state.state_version;
    const last = [...context.recent_turns].reverse().find((t) => t.role === "agent");
    this.lastAnswer = last?.text ?? this.lastAnswer;
  }

  on<K extends keyof EngineEvents>(e: K, cb: (ev: EngineEvent<K>) => void): () => void {
    const set = (this.listeners[e] ??= new Set() as never) as Set<(ev: EngineEvent<K>) => void>;
    set.add(cb);
    return () => set.delete(cb);
  }

  // ── Plumbing ───────────────────────────────────────────────────────────────

  private now(): number {
    return this.deps.now();
  }

  private emit<K extends keyof EngineEvents>(type: K, payload: EngineEvents[K]): void {
    const ev: EngineEvent<K> = {
      schema_version: "1",
      event_id: crypto.randomUUID(),
      seq: ++this.seq,
      conversation_id: this.conversationId,
      turn_id: this.turnId,
      state_version: this.stateVersion,
      generation_id: this.generationId,
      type,
      t: this.now(),
      payload,
    };
    const set = this.listeners[type] as Set<(ev: EngineEvent<K>) => void> | undefined;
    set?.forEach((cb) => cb(ev));
  }

  private sleep(ms: number, run: number): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.timers.delete(timer);
        if (run === this.run) resolve();
        else reject(new Cancelled());
      }, ms);
      this.timers.add(timer);
    });
  }

  /** Invalidates every pending step of the current run. */
  private cancel(): void {
    this.run++;
    for (const t of this.timers) clearTimeout(t);
    this.timers.clear();
  }

  private launch(fn: (run: number) => Promise<void>, run: number): void {
    fn(run).catch((err: unknown) => {
      if (!(err instanceof Cancelled)) {
        this.emit("error", { code: "ENGINE_DROPPED", message: "El motor simulado falló de forma inesperada.", retryable: true });
        this.emit("status", { state: "error" });
      }
    });
  }

  private alive(run: number): void {
    if (run !== this.run) throw new Cancelled();
  }

  // ── Speech ─────────────────────────────────────────────────────────────────

  private playedMs(): number {
    return this.speaking ? this.now() - this.speaking.tStart : 0;
  }

  /** Emits the agent's words as they are "played"; the text runs slightly ahead of the audio. */
  private async speak(text: string, kind: SpeechKind, run: number, interruptAfterWords?: number): Promise<boolean> {
    const generationId = crypto.randomUUID();
    const words = text.split(/\s+/);
    this.generationId = generationId;
    const sp: Speaking = { generationId, utteranceId: crypto.randomUUID(), words, heard: 0, shown: 0, tStart: this.now(), kind };
    this.speaking = sp;
    this.emit("status", { state: "speaking" });
    this.emit("speech", { phase: "start", generation_id: generationId, kind });
    while (sp.heard < words.length) {
      sp.shown = Math.min(words.length, sp.heard + TEXT_LEAD_WORDS);
      this.emitAgentText(sp, false);
      await this.sleep(WORD_MS, run);
      sp.heard++;
      if (interruptAfterWords !== undefined && sp.heard >= interruptAfterWords) return false;
    }
    sp.shown = words.length;
    this.emitAgentText(sp, true);
    this.emit("speech", { phase: "stop", generation_id: generationId, kind });
    this.speaking = null;
    this.generationId = null;
    if (kind === "answer") this.lastAnswer = text;
    return true;
  }

  private emitAgentText(sp: Speaking, final: boolean): void {
    this.emit("transcript", {
      role: "agent",
      utterance_id: sp.utteranceId,
      text: sp.words.slice(0, sp.shown).join(" "),
      final,
      t_start: sp.tStart,
      t_end: this.now(),
      t_source: "engine",
    });
  }

  /**
   * Stops the active generation (docs/08 §6): fixes what was heard, keeps the
   * rest as diagnostic text, and drops anything later from that generation.
   */
  private cutSpeech(playedMs: number): void {
    const sp = this.speaking;
    if (!sp) return;
    const delivered = sp.words.slice(0, sp.heard).join(" ");
    // `interrupted` closes the generation: it is the first sign of the cut and nothing with
    // that generation_id follows it (docs/08 §6.5). The store closes the utterance from it.
    this.emit("interrupted", { generation_id: sp.generationId, played_ms: Math.round(playedMs), delivered_text: delivered });
    if (delivered) this.lastAnswer = delivered;
    // Bookkeeping that closes the utterance and the speech goes out detached from the
    // generation (envelope generation_id = null), so the interrupted id never reappears.
    this.generationId = null;
    this.emitAgentText(sp, true);
    this.emit("speech", { phase: "stop", generation_id: sp.generationId, kind: sp.kind });
    this.speaking = null;
    if (this.latency) {
      // Simulated local stop: the playback queue is flushed a few tens of ms after detection.
      this.latency.t_playback_stop = this.now() + 40 + Math.round(Math.random() * 60);
      this.emit("latency", this.latency);
    }
  }

  // ── Turns ──────────────────────────────────────────────────────────────────

  private newTurn(): string {
    this.turnId = crypto.randomUUID();
    this.latency = null;
    return this.turnId;
  }

  /** A spoken user utterance: partials while "talking", then the final text. */
  private async userSpeaks(text: string, run: number): Promise<string> {
    this.newTurn();
    const utteranceId = crypto.randomUUID();
    const words = text.split(/\s+/);
    const tStart = this.now();
    this.emit("status", { state: "listening" });
    for (let i = 1; i <= words.length; i++) {
      await this.sleep(PARTIAL_MS, run);
      this.emit("transcript", {
        role: "user",
        utterance_id: utteranceId,
        text: words.slice(0, i).join(" "),
        final: i === words.length,
        t_start: tStart,
        t_end: this.now(),
        t_source: "engine",
      });
    }
    this.latency = { t_speech_end: this.now() };
    return utteranceId;
  }

  private async callTool(name: ToolName, args: Record<string, unknown>, run: number): Promise<EvidenceEnvelope> {
    const call: ToolCallPayload = { tool_call_id: crypto.randomUUID(), name, args };
    this.emit("status", { state: "thinking" });
    this.emit("tool_call", call);
    const tStart = this.now();
    const env = await this.deps.runTool(call, {
      conversation_id: this.conversationId,
      turn_id: this.turnId ?? "",
      state_version: this.stateVersion,
    });
    const current = run === this.run;
    if (current && this.latency && name !== "correct_context") {
      this.latency.t_tool_start = tStart;
      this.latency.t_tool_end = this.now();
    }
    if (env.status === "ok") this.stateVersion = Math.max(this.stateVersion, env.state_version);
    // Every tool_call gets its tool_result, even when a newer turn superseded this one.
    this.emit("tool_result", {
      tool_call_id: call.tool_call_id,
      status: env.status,
      trace: { soql: env.trace.soql, ms: env.trace.ms, rows: env.trace.rows, cache_status: env.evidence.cache_status },
      evidence_ref: env.evidence.query_fingerprint,
    });
    this.alive(run);
    return env;
  }

  /** Acknowledgement → tool → answer, with the latency marks of docs/08 §9. */
  private async respond(reply: Reply, run: number, ack: string | undefined = reply.ack): Promise<void> {
    this.emit("status", { state: "thinking" });
    await this.sleep(260, run);
    let env: EvidenceEnvelope | null = null;
    if (reply.tool) {
      if (ack) {
        if (this.latency) this.latency.t_ack_audio = this.now();
        await this.speak(ack, "ack", run);
      }
      env = await this.callTool(reply.tool.name, reply.tool.args, run);
    }
    await this.sleep(180, run);
    if (this.latency) this.latency.t_first_useful_audio = this.now();
    const text = reply.say(env, this.style?.style === "directo");
    const finished = await this.speak(text, "answer", run, reply.interruptAfterWords);
    if (!finished) return; // the caller handles the barge-in
    if (this.latency) this.emit("latency", this.latency);
    this.emit("status", { state: "listening" });
  }

  private async textTurn(text: string, run: number): Promise<void> {
    this.newTurn();
    const utteranceId = crypto.randomUUID();
    const t = this.now();
    this.emit("transcript", { role: "user", utterance_id: utteranceId, text, final: true, t_start: t, t_end: t, t_source: "local" });
    this.latency = { t_speech_end: t };
    if (/repit|repet|otra vez/.test(fold(text))) {
      const again = this.lastAnswer;
      await this.respond({ say: () => again ?? "Todavía no he dado ninguna respuesta que pueda repetir." }, run);
      return;
    }
    await this.respond(pickReply(text), run);
  }

  // ── Script ─────────────────────────────────────────────────────────────────

  private async playScript(run: number): Promise<void> {
    await this.sleep(1200, run);
    await this.userSpeaks("¿Qué municipios tienen más camas?", run);
    await this.respond(REPLIES.topBeds, run);

    await this.sleep(1500, run);
    const asked = await this.userSpeaks("¿Cuántas camas hay en Medellín?", run);
    const askedTurn = this.turnId;
    await this.respond({ ...bedsIn("MEDELLÍN", "Medellín"), interruptAfterWords: 9 }, run);

    // The user barges in: playback stops first, then the new utterance opens a turn (R-24).
    this.cutSpeech(this.playedMs());
    await this.userSpeaks("No, dije Melgar.", run);
    const t = this.now();
    this.emit("transcript", {
      role: "user",
      utterance_id: crypto.randomUUID(),
      text: "¿Cuántas camas hay en Melgar?",
      final: true,
      t_start: t,
      t_end: t,
      t_source: "engine",
      corrects: asked,
    });
    const fix = await this.callTool(
      "correct_context",
      { target_turn_id: askedTurn, expected_state_version: this.stateVersion, field: "municipality", value: "Melgar" },
      run,
    );
    const resolved = ok(fix) && typeof fix.data?.resolved === "string" ? fix.data.resolved : "Melgar";
    await this.respond(bedsIn("MELGAR", resolved), run, `Gracias por corregirme; consultaré ${resolved}.`);

    if (this.opts.dropAtEnd) {
      await this.sleep(1600, run);
      this.emit("error", { code: "ENGINE_DROPPED", message: "El motor cerró la conexión (corte simulado).", retryable: true });
    }
  }
}
