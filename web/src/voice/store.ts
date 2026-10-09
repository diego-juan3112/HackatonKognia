/**
 * Small event store for the console.
 *
 * Engine events (docs/08 §2) and analyst output (docs/10 §6) are folded into one
 * plain state object. Panels subscribe and re-render the slice that changed.
 * The store is a module singleton, so it survives Astro view transitions.
 */
import type {
  AffectEstimate,
  AnyEngineEvent,
  CacheStatus,
  EngineEvents,
  EngineId,
  EngineStatus,
  ErrorPayload,
  EvidenceEnvelope,
  Sentiment,
  SessionPayload,
  SpeechKind,
  StyleDecision,
  TimeSource,
  ToolCallPayload,
  ToolStatus,
  ToolTrace,
  TranscriptRole,
  VoiceMode,
} from "./types";

export interface Utterance {
  id: string;
  role: TranscriptRole;
  text: string;
  final: boolean;
  t_start: number;
  t_end: number;
  t_source: TimeSource;
  speaker?: string;
  turn_id: string | null;
  generation_id: string | null;
  kind?: SpeechKind;
  /** Set when the agent was interrupted: only this part was actually heard. */
  delivered_text?: string;
  /** Figures the backend could not find in the tool results of the turn (POST /verify/answer). */
  unverified?: number[];
  /** Set when a later utterance corrected this one; the original text is kept. */
  correction?: { text: string; reason: string; t: number };
}

export interface ToolEntry {
  tool_call_id: string;
  name: ToolCallPayload["name"];
  args: Record<string, unknown>;
  turn_id: string | null;
  state_version: number;
  t_call: number;
  status?: ToolStatus;
  trace?: ToolTrace;
  evidence_ref?: string;
  /** Evidence superseded by a correction (A-09). */
  invalidated: boolean;
  requery?: { pending: boolean; matches?: boolean; ms?: number; at?: number };
}

export interface AffectEntry {
  utterance_id: string;
  text: string;
  t: number;
  estimate: AffectEstimate;
  /** Per-channel readings shown side by side when they disagree. */
  channels?: { text?: Pick<AffectEstimate, "sentiment" | "emotion" | "state_hint">; voice?: Pick<AffectEstimate, "sentiment" | "emotion" | "state_hint"> };
  analysis_ms: number | null;
  /** Style decided by the backend analyst for the next turn, when it returns one. */
  style?: StyleDecision;
}

export interface TurnMetrics {
  turn_id: string;
  n: number;
  engine: EngineId;
  model: string;
  question: string;
  ack_ms: number | null;
  /** Offset of the tool call from the end of the user's speech. */
  tool_start_ms: number | null;
  tool_ms: number | null;
  rows: number | null;
  cache: CacheStatus | null;
  first_useful_ms: number | null;
  stop_ms: number | null;
  interrupted_at: number | null;
  attempts: number;
  analysis_ms: number | null;
}

export interface Notice {
  id: string;
  t: number;
  kind: "session" | "error" | "info";
  text: string;
  /** Shows «Reintentar»: the session could not start. */
  retry?: boolean;
}

export interface ConsoleState {
  running: boolean;
  status: EngineStatus;
  engine: EngineId;
  model: string;
  simulated: boolean;
  conversation_id: string | null;
  state_version: number;
  utterances: Utterance[];
  tools: ToolEntry[];
  evidence: Record<string, EvidenceEnvelope>;
  affect: AffectEntry[];
  style: StyleDecision;
  /** Consecutive inferred signals pointing at a style that is not active yet. */
  styleSignal: { hint: string; count: number; needed: number } | null;
  turns: TurnMetrics[];
  notices: Notice[];
  lastError: ErrorPayload | null;
  voiceAnalysis: boolean;
  voiceMode: VoiceMode;
  /** Voices the backend offers (`GET /health` → `voice_modes`, docs/08 §3). */
  voiceModes: VoiceMode[];
  speakingKind: SpeechKind | null;
  /** Tool catalogue announced by `GET /health` (docs/08 §3). */
  toolCatalog: { name: string; description: string }[];
  /** Model ids announced by the backend, per engine. */
  engineModels: Partial<Record<string, string>>;
}

export type Slice = "status" | "transcript" | "tools" | "affect" | "style" | "latency" | "notices" | "meta" | "reset";
type Listener = (state: ConsoleState, slices: ReadonlySet<Slice>) => void;

export const NEUTRAL_STYLE: StyleDecision = {
  style: "neutro",
  directives: [],
  reason: "Estilo por defecto: aún no hay señales ni preferencias.",
  source: "inferred",
  applies_from_turn: 1,
};

function initialState(): ConsoleState {
  return {
    running: false,
    status: "idle",
    engine: "openai",
    model: "",
    simulated: true,
    conversation_id: null,
    state_version: 1,
    utterances: [],
    tools: [],
    evidence: {},
    affect: [],
    style: NEUTRAL_STYLE,
    styleSignal: null,
    turns: [],
    notices: [],
    lastError: null,
    // Off until the person presses «Usar mi voz» (R-26). Audio is never stored.
    voiceAnalysis: false,
    voiceMode: "engine",
    voiceModes: ["engine"],
    speakingKind: null,
    toolCatalog: [],
    engineModels: {},
  };
}

let state: ConsoleState = initialState();
const seenEvents = new Set<string>();
const listeners = new Set<Listener>();
let pending: Set<Slice> | null = null;

/** Coalesces bursts of events (partials arrive every ~100 ms) into one render per frame. */
function notify(...slices: Slice[]): void {
  if (!pending) {
    pending = new Set();
    const flush = (): void => {
      const batch = pending ?? new Set<Slice>();
      pending = null;
      for (const l of listeners) l(state, batch);
    };
    if (typeof requestAnimationFrame === "function" && !document.hidden) requestAnimationFrame(flush);
    else setTimeout(flush, 0);
  }
  for (const s of slices) pending.add(s);
}

export function getState(): ConsoleState {
  return state;
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const uid = (): string => crypto.randomUUID();

function turnFor(turn_id: string | null): TurnMetrics | undefined {
  return turn_id ? state.turns.find((t) => t.turn_id === turn_id) : undefined;
}

function ensureTurn(turn_id: string, question: string): TurnMetrics {
  let turn = turnFor(turn_id);
  if (!turn) {
    turn = {
      turn_id,
      n: state.turns.length + 1,
      engine: state.engine,
      model: state.model,
      question,
      ack_ms: null,
      tool_start_ms: null,
      tool_ms: null,
      rows: null,
      cache: null,
      first_useful_ms: null,
      stop_ms: null,
      interrupted_at: null,
      attempts: 1,
      analysis_ms: null,
    };
    state.turns.push(turn);
  } else if (question) {
    turn.question = question;
  }
  return turn;
}

function addNotice(kind: Notice["kind"], text: string, t: number): void {
  state.notices.push({ id: uid(), t, kind, text });
  if (state.notices.length > 30) state.notices.shift();
}

const ENGINE_LABEL: Record<EngineId, string> = { openai: "OpenAI Realtime", gemini: "Gemini Live" };

const isEngine = (v: unknown): v is EngineId => v === "openai" || v === "gemini";

function sessionText(p: SessionPayload): string {
  if (p.event === "voice_changed") return `Voz cambiada a ${p.to === "cloned" ? "la voz clonada" : "la del motor"} (${p.reason}).`;
  if (p.event === "expiring") return `La sesión está por vencer: se renovará entre turnos (${p.reason}).`;
  if (p.event === "switched") return `Sesión renovada: motor cambiado a ${isEngine(p.to) ? ENGINE_LABEL[p.to] : "otro motor"} (${p.reason}). No se repitió ninguna consulta.`;
  return `Sesión renovada con el mismo motor (${p.reason}).`;
}

const handlers: { [K in keyof EngineEvents]: (ev: Extract<AnyEngineEvent, { type: K }>) => Slice[] } = {
  status(ev) {
    state.status = ev.payload.state;
    if (ev.payload.state !== "speaking") state.speakingKind = null;
    return ["status"];
  },

  transcript(ev) {
    const p = ev.payload;
    if (p.corrects) {
      const original = state.utterances.find((u) => u.id === p.corrects);
      if (original) original.correction = { text: p.text, reason: "Corregido por el usuario", t: p.t_end };
      return ["transcript"];
    }
    if (p.retracted) {
      // Noise the recognizer turned into text: its partial bubble goes away.
      const i = state.utterances.findIndex((x) => x.id === p.utterance_id);
      if (i < 0) return [];
      state.utterances.splice(i, 1);
      return ["transcript"];
    }
    let u = state.utterances.find((x) => x.id === p.utterance_id);
    if (!u) {
      u = {
        id: p.utterance_id,
        role: p.role,
        text: p.text,
        final: p.final,
        t_start: p.t_start,
        t_end: p.t_end,
        t_source: p.t_source,
        speaker: p.speaker,
        turn_id: ev.turn_id,
        generation_id: ev.generation_id,
        kind: p.role === "agent" ? (state.speakingKind ?? undefined) : undefined,
      };
      state.utterances.push(u);
    } else {
      // Interrupted: anything that still arrives for that generation is dropped (docs/08 §6.5).
      if (u.role === "agent" && u.delivered_text !== undefined) return [];
      u.text = p.text;
      u.final = p.final;
      // A question echoed before the engine took it gets its turn when the engine opens one.
      if (u.turn_id === null) u.turn_id = ev.turn_id;
      u.t_end = p.t_end;
      if (p.speaker) u.speaker = p.speaker;
    }
    const slices: Slice[] = ["transcript"];
    if (p.role === "user" && p.final && ev.turn_id) {
      ensureTurn(ev.turn_id, p.text);
      slices.push("latency");
    }
    return slices;
  },

  tool_call(ev) {
    state.tools.push({
      tool_call_id: ev.payload.tool_call_id,
      name: ev.payload.name,
      args: ev.payload.args,
      turn_id: ev.turn_id,
      state_version: ev.state_version,
      t_call: ev.t,
      invalidated: false,
    });
    return ["tools"];
  },

  tool_result(ev) {
    const p = ev.payload;
    const entry = state.tools.find((t) => t.tool_call_id === p.tool_call_id);
    if (!entry) return [];
    entry.status = p.status;
    entry.trace = p.trace;
    entry.evidence_ref = p.evidence_ref;
    // A successful correction supersedes the evidence of the corrected turn (A-09).
    if (entry.name === "correct_context" && p.status === "ok") {
      const target = entry.args.target_turn_id;
      for (const t of state.tools) if (t.turn_id === target && t !== entry) t.invalidated = true;
    }
    const turn = turnFor(ev.turn_id);
    if (turn && entry.name !== "correct_context") {
      turn.rows = p.trace.rows;
      turn.cache = p.trace.cache_status;
    }
    return ["tools", "latency"];
  },

  speech(ev) {
    state.speakingKind = ev.payload.phase === "start" ? ev.payload.kind : null;
    // A real engine only learns that a phrase was an acknowledgement when the tool call
    // follows it, so the kind of an utterance already on screen can still change.
    const u = state.utterances.find((x) => x.role === "agent" && x.generation_id === ev.payload.generation_id);
    if (u && u.kind !== ev.payload.kind) {
      u.kind = ev.payload.kind;
      return ["status", "transcript"];
    }
    return ["status"];
  },

  interrupted(ev) {
    const u = state.utterances.find((x) => x.generation_id === ev.payload.generation_id && x.role === "agent");
    if (u) {
      u.delivered_text = ev.payload.delivered_text;
      u.final = true;
    }
    // No `speech stop` follows an interruption: the generation ends here.
    state.speakingKind = null;
    const turn = turnFor(ev.turn_id);
    if (turn) turn.interrupted_at = ev.t;
    return ["transcript"];
  },

  latency(ev) {
    const p = ev.payload;
    if (!ev.turn_id) return [];
    const turn = ensureTurn(ev.turn_id, "");
    const since = (t: number | undefined): number | null => (t === undefined ? null : Math.max(0, Math.round(t - p.t_speech_end)));
    turn.ack_ms = since(p.t_ack_audio);
    turn.first_useful_ms = since(p.t_first_useful_audio);
    turn.tool_start_ms = since(p.t_tool_start);
    turn.tool_ms = p.t_tool_start !== undefined && p.t_tool_end !== undefined ? Math.round(p.t_tool_end - p.t_tool_start) : null;
    // Interruption stop time: speech detected (the `interrupted` event) → playback stopped.
    if (p.t_playback_stop !== undefined && turn.interrupted_at !== null) {
      turn.stop_ms = Math.max(0, Math.round(p.t_playback_stop - turn.interrupted_at));
    }
    return ["latency"];
  },

  session(ev) {
    const p = ev.payload;
    if (p.event === "switched" && isEngine(p.to)) state.engine = p.to;
    if (p.event === "voice_changed" && (p.to === "engine" || p.to === "cloned")) state.voiceMode = p.to;
    if (p.event === "renewed" || p.event === "switched") {
      const turn = turnFor(ev.turn_id) ?? state.turns[state.turns.length - 1];
      if (turn) turn.attempts = Math.max(turn.attempts, p.attempt + 1);
    }
    addNotice("session", sessionText(p), ev.t);
    return ["notices", "meta", "latency"];
  },

  error(ev) {
    state.lastError = ev.payload;
    addNotice("error", ev.payload.message, ev.t);
    return ["notices", "status"];
  },
};

/** Folds one engine event into the state. */
export function dispatch(ev: AnyEngineEvent): void {
  if (ev.conversation_id !== state.conversation_id) return; // late event from a previous session
  // A re-sent event keeps its event_id (docs/08 §2): it is folded only once.
  if (seenEvents.has(ev.event_id)) return;
  seenEvents.add(ev.event_id);
  if (seenEvents.size > 4000) {
    const oldest = seenEvents.values().next().value;
    if (oldest !== undefined) seenEvents.delete(oldest);
  }
  state.state_version = Math.max(state.state_version, ev.state_version);
  const handler = handlers[ev.type] as (e: AnyEngineEvent) => Slice[];
  notify(...handler(ev));
}

// ── Mutations that do not come from the engine ───────────────────────────────

export function beginSession(conversation_id: string, engine: EngineId, model: string, simulated: boolean): void {
  const keep = { voiceAnalysis: state.voiceAnalysis, voiceMode: state.voiceMode, voiceModes: state.voiceModes, toolCatalog: state.toolCatalog, engineModels: state.engineModels };
  seenEvents.clear();
  state = { ...initialState(), ...keep, running: true, conversation_id, engine, model, simulated };
  notify("reset");
}

/** Reopens a stopped conversation: the transcript and everything derived from it stay. */
export function resumeSession(engine: EngineId, model: string, simulated: boolean): void {
  state.running = true;
  state.status = "connecting";
  state.engine = engine;
  state.model = model;
  state.simulated = simulated;
  notify("status", "meta");
}

export function endSession(): void {
  // Nothing else will arrive: close every partial so no bubble stays "writing" (docs/08 §10).
  let closed = false;
  for (const u of state.utterances) {
    if (u.final) continue;
    u.final = true;
    closed = true;
  }
  if (closed) notify("transcript");
  state.running = false;
  state.status = "idle";
  state.speakingKind = null;
  notify("status", "meta");
}

export function reset(): void {
  // Engine and voice choices are settings, not conversation state.
  const keep = { engine: state.engine, model: state.model, simulated: state.simulated, voiceMode: state.voiceMode, voiceModes: state.voiceModes, toolCatalog: state.toolCatalog, engineModels: state.engineModels };
  state = { ...initialState(), ...keep };
  notify("reset");
}

export function setEngine(engine: EngineId, model: string, simulated: boolean): void {
  state.engine = engine;
  // The backend's model id wins over the one fixed in the client (GET /health).
  state.model = (!simulated && state.engineModels[engine]) || model;
  state.simulated = simulated;
  notify("meta");
}

export function setStatus(status: EngineStatus): void {
  state.status = status;
  notify("status");
}

export function setVoiceAnalysis(on: boolean): void {
  state.voiceAnalysis = on;
  notify("meta", "affect");
}

export function setHealth(tools: ConsoleState["toolCatalog"], models: ConsoleState["engineModels"]): void {
  state.toolCatalog = tools;
  state.engineModels = models;
  const m = models[state.engine];
  if (m && state.model !== m && !state.simulated) state.model = m;
  notify("meta", "tools");
}

export function setVoiceMode(mode: VoiceMode): void {
  state.voiceMode = mode;
  notify("meta");
}

/** Voices announced by the backend; a mode that is no longer offered falls back to the engine voice. */
export function setVoiceModes(modes: VoiceMode[]): void {
  state.voiceModes = modes.includes("engine") ? modes : ["engine", ...modes];
  if (!state.voiceModes.includes(state.voiceMode)) state.voiceMode = "engine";
  notify("meta");
}

/** Marks figures of an agent utterance as not verified against the evidence. */
export function markUnverified(utterance_id: string, numbers: number[]): void {
  const u = state.utterances.find((x) => x.id === utterance_id);
  if (!u || numbers.length === 0) return;
  u.unverified = numbers;
  notify("transcript");
}

export function putEvidence(env: EvidenceEnvelope): void {
  state.evidence[env.evidence.query_fingerprint] = env;
}

export function pushAffect(entry: AffectEntry): void {
  state.affect.push(entry);
  const turn = turnFor(entry.estimate.turn_id);
  if (turn) turn.analysis_ms = entry.analysis_ms;
  notify("affect", "latency");
}

export function setStyle(style: StyleDecision, signal: ConsoleState["styleSignal"] = null): void {
  state.style = style;
  state.styleSignal = signal;
  notify("style");
}

export function setStyleSignal(signal: ConsoleState["styleSignal"]): void {
  state.styleSignal = signal;
  notify("style");
}

export function setRequery(tool_call_id: string, requery: ToolEntry["requery"]): void {
  const entry = state.tools.find((t) => t.tool_call_id === tool_call_id);
  if (!entry) return;
  entry.requery = requery;
  notify("tools");
}

export function invalidateTurn(turn_id: string | null): void {
  for (const t of state.tools) if (t.turn_id === turn_id) t.invalidated = true;
  notify("tools");
}

export function pushNotice(kind: Notice["kind"], text: string, t = 0, retry = false): void {
  addNotice(kind, text, t);
  if (retry) state.notices[state.notices.length - 1]!.retry = true;
  notify("notices");
}

/** Drops the error notices of the current conversation (before one human-readable notice replaces them). */
export function clearErrors(): void {
  state.notices = state.notices.filter((n) => n.kind !== "error");
  notify("notices");
}

/** Valence used by the affect line: +1 / 0 / −1, or null (a gap) when uncertain. */
export function valence(sentiment: Sentiment): number | null {
  if (sentiment === "positive") return 1;
  if (sentiment === "negative") return -1;
  if (sentiment === "neutral") return 0;
  return null;
}
