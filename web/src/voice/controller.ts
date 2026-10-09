/**
 * Conversation controller: owns the active VoiceEngine and wires it to the store.
 *
 * It is the only module that talks to both. Panels call these functions; they
 * never touch an engine. Responsibilities (docs/08 §5–§7, docs/10 §5–§6):
 * tool bridge with idempotency, engine switch with a neutral context envelope,
 * analyst calls, style decisions and the user controls.
 */
import { analyze, DIRECTIVES, inferStyle } from "./analyst";
import { fetchBrief, fetchVoiceModes, runTool, type ToolContext } from "./api";
import { getMicTap } from "./audio/mic-tap";
import { createEngine, engineInfo, engineLabel, otherEngine } from "./engine-factory";
import type { EngineDeps } from "./fake-engine";
import * as store from "./store";
import type {
  AnyEngineEvent,
  ContextEnvelope,
  EngineEvents,
  EngineId,
  EvidenceEnvelope,
  StyleDecision,
  ToolCallPayload,
  ToolName,
  VoiceEngine,
  VoiceMode,
} from "./types";

const EVENT_TYPES: (keyof EngineEvents)[] = [
  "status",
  "transcript",
  "tool_call",
  "tool_result",
  "speech",
  "interrupted",
  "latency",
  "session",
  "error",
];

const MAX_ENGINE_ATTEMPTS = 2; // per turn (R-25)
const ALLOWED_TOOLS: ToolName[] = ["search_ips", "get_ips_details", "aggregate_ips", "compare_ips", "correct_context"];

let engine: VoiceEngine | null = null;
let unsubscribe: (() => void)[] = [];
let sessionStart = 0;
let localSeq = 0;
let firstQuery = true;
let attemptsThisTurn = 1;
let pendingQuestion: string | null = null;
/** Question shown at once while the engine is still busy with the brief. */
let pendingEcho: { id: string; text: string; shown: boolean } | null = null;

/** Shows the early question once the greeting is on screen, so the order reads brief → question. */
function showEcho(): void {
  if (!pendingEcho || pendingEcho.shown) return;
  pendingEcho.shown = true;
  const t = now();
  localEvent("transcript", { role: "user", utterance_id: pendingEcho.id, text: pendingEcho.text, final: true, t_start: t, t_end: t, t_source: "local" });
}

const foldText = (s: string): string =>
  s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

/** «Sé más directo», spoken or typed: an explicit preference, applied at once (docs/10 §6, A-14). */
const ASKS_DIRECT =
  /\b(se|sea|seas|responde|respondeme|contesta|contestame|habla|hablame)\b[^.?!]*\b(direct[oa]s?|breves?|concis[oa]s?|cort[oa]s?)\b|\bmas (direct[oa]|breve|cort[oa]|concis[oa])\b|\bal grano\b|\bsin rodeos\b/;

function preferDirectIfAsked(text: string): void {
  if (!ASKS_DIRECT.test(foldText(text))) return;
  const s = store.getState();
  if (s.style.source === "preference" && s.style.style === "directo") return;
  const decision: StyleDecision = {
    style: "directo",
    directives: DIRECTIVES.directo,
    reason: "Lo pediste: una o dos frases, con la cifra primero.",
    source: "preference",
    applies_from_turn: s.turns.length + 1,
  };
  store.setStyle(decision);
  engine?.applyStyle(decision);
}
const toolCache = new Map<string, Promise<EvidenceEnvelope>>();
/** Canonical state kept by the browser between tool calls (docs/10 §4). */
let confirmedFilters: Record<string, unknown> = {};
let selectedSiteKeys: string[] = [];

/** The full canonical context the backend needs: it keeps no state of its own. */
function canonicalContext(ctx: ToolContext): ToolContext {
  const s = store.getState();
  return {
    ...ctx,
    locale: "es-CO",
    confirmed_filters: confirmedFilters,
    selected_site_keys: selectedSiteKeys,
    tone_preference: tonePreference(),
    last_evidence_refs: s.tools.filter((t) => t.status === "ok" && !t.invalidated && t.evidence_ref).slice(-5).map((t) => t.evidence_ref),
  };
}

function tonePreference(): "concise" | "neutral" {
  const s = store.getState();
  return s.style.source === "preference" && s.style.style === "directo" ? "concise" : "neutral";
}

function applyPatch(env: EvidenceEnvelope): void {
  if (env.status !== "ok") return;
  const patch = env.context_patch ?? {};
  if (patch.confirmed_filters && typeof patch.confirmed_filters === "object") confirmedFilters = patch.confirmed_filters;
  else if (Object.keys(env.evidence.filters ?? {}).length > 0) confirmedFilters = env.evidence.filters;
  if (Array.isArray(patch.selected_site_keys)) selectedSiteKeys = patch.selected_site_keys.filter((k): k is string => typeof k === "string");
}

const now = (): number => Math.round(performance.now() - sessionStart);

// ── Tool bridge ──────────────────────────────────────────────────────────────

const deps: EngineDeps = {
  now,
  getBrief: async () => (await fetchBrief()).brief,
  runTool(call: ToolCallPayload, ctx: ToolContext): Promise<EvidenceEnvelope> {
    // Idempotency: same tool_call_id + state_version reuses the result (docs/08 §5.5).
    const key = `${call.tool_call_id}:${ctx.state_version}`;
    const cached = toolCache.get(key);
    if (cached) return cached;
    const forceLive = firstQuery;
    firstQuery = false;
    const result = runTool(call, canonicalContext(ctx), { forceLive }).then((env) => {
      store.putEvidence(env);
      applyPatch(env);
      return env;
    });
    toolCache.set(key, result);
    return result;
  },
};

// ── Engine wiring ────────────────────────────────────────────────────────────

function attach(e: VoiceEngine): void {
  detach();
  engine = e;
  unsubscribe = EVENT_TYPES.map((type) =>
    e.on(type, (ev) => {
      if (engine !== e) return; // late event from an engine that was replaced
      // `seq` is monotonic per session, across engines and local events (docs/08 §2).
      let event = { ...(ev as AnyEngineEvent), seq: ++localSeq } as AnyEngineEvent;
      // The engine now takes the question that was echoed early: same bubble, not a second one.
      if (event.type === "transcript" && pendingEcho && event.payload.role === "user" && event.payload.text === pendingEcho.text) {
        if (pendingEcho.shown) event = { ...event, payload: { ...event.payload, utterance_id: pendingEcho.id } };
        pendingEcho = null;
      }
      store.dispatch(event);
      // As soon as the greeting starts (not when it ends) the question appears below it.
      if (event.type === "transcript" && event.payload.role === "agent") showEcho();
      else if (event.type === "status" && event.payload.state === "listening") showEcho();
      afterEvent(event);
    }),
  );
}

function detach(): void {
  for (const off of unsubscribe) off();
  unsubscribe = [];
}

/** Events the controller raises itself (engine switch) use the same envelope. */
function localEvent<K extends keyof EngineEvents>(type: K, payload: EngineEvents[K]): void {
  const s = store.getState();
  if (!s.conversation_id) return;
  const lastTurn = s.turns[s.turns.length - 1];
  store.dispatch({
    schema_version: "1",
    event_id: crypto.randomUUID(),
    seq: ++localSeq,
    conversation_id: s.conversation_id,
    turn_id: lastTurn?.turn_id ?? null,
    state_version: s.state_version,
    generation_id: null,
    type,
    t: now(),
    payload,
  } as AnyEngineEvent);
}

function afterEvent(ev: AnyEngineEvent): void {
  if (ev.type === "transcript") {
    const p = ev.payload;
    if (p.role === "user" && p.final && !p.corrects && ev.turn_id) {
      attemptsThisTurn = 1;
      preferDirectIfAsked(p.text);
      void runAnalysis(p.utterance_id, p.text, ev.turn_id, ev.state_version, p.t_start, p.t_end, p.t_source !== "local");
    }
  } else if (ev.type === "status") {
    if (ev.payload.state === "listening" && pendingQuestion) {
      const q = pendingQuestion;
      pendingQuestion = null;
      engine?.sendText(q);
    }
  } else if (ev.type === "error") {
    const code = ev.payload.code;
    if (ev.payload.retryable && (code === "ENGINE_DROPPED" || code === "ENGINE_CONNECT_FAILED" || code === "ENGINE_QUOTA")) {
      void switchEngine(otherEngine(store.getState().engine), code, true);
    }
  }
}

// ── Analyst and style ────────────────────────────────────────────────────────

/** WAV of the utterance (±250 ms) from the 30 s mic ring, base64. Null when there is none. */
async function utteranceClip(tStart: number, tEnd: number): Promise<string | null> {
  const mic = getMicTap();
  if (!mic.active || tEnd <= tStart) return null;
  const blob = mic.slice(tStart - 250, tEnd + 250);
  if (!blob) return null;
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

async function runAnalysis(utterance_id: string, text: string, turn_id: string, state_version: number, t: number, tEnd: number = t, spoken = false): Promise<void> {
  const before = store.getState();
  const conversation = before.conversation_id;
  const consent = before.voiceAnalysis;
  // The clip leaves the browser only with consent, and only for a spoken utterance.
  const audioWavB64 = consent && spoken && !before.simulated ? await utteranceClip(t, tEnd).catch(() => null) : null;
  const turn = before.turns.find((x) => x.turn_id === turn_id);
  const entry = await analyze({
    utterance_id,
    text,
    turn_id,
    state_version,
    t,
    voiceConsent: consent,
    t_start: t,
    t_end: tEnd,
    signals: {
      spoken,
      interrupted_agent: before.turns.some((x) => x.interrupted_at !== null && x.n === (turn?.n ?? before.turns.length) - 1),
      is_correction: /^\s*(no[, ]|corrección|dije )/i.test(text),
      engine_attempts: attemptsThisTurn,
    },
    audioWavB64,
    affectHistory: before.affect.slice(-3).map((a) => a.estimate),
    tonePreference: tonePreference(),
    currentStyle: before.style,
    turnIndex: turn?.n ?? before.turns.length,
  });
  const s = store.getState();
  if (s.conversation_id !== conversation) return; // the session was restarted meanwhile
  store.pushAffect(entry);
  if (entry.style) {
    // The backend applied the style policy (docs/10 §6). An explicit preference still wins here.
    const changed = entry.style.style !== s.style.style || entry.style.directives.join("|") !== s.style.directives.join("|");
    if (changed && !(s.style.source === "preference" && entry.style.source !== "preference")) {
      store.setStyle(entry.style);
      engine?.applyStyle(entry.style);
    }
    return;
  }
  const outcome = inferStyle(
    s.affect.map((a) => a.estimate),
    s.style,
    s.turns.length + 1,
  );
  if (outcome.decision) {
    store.setStyle(outcome.decision);
    engine?.applyStyle(outcome.decision);
  } else {
    store.setStyleSignal(outcome.signal);
  }
}

// ── Context envelope (docs/10 §3) ────────────────────────────────────────────

function buildEnvelope(): ContextEnvelope {
  const s = store.getState();
  // Only finished utterances, and only what was actually heard.
  const recent = s.utterances
    .filter((u) => u.final && u.kind !== "ack")
    .slice(-8)
    .map((u) => ({ role: u.role, text: u.correction?.text ?? u.delivered_text ?? u.text }))
    .filter((u) => u.text.trim() !== "");
  const results = s.tools
    .filter((t) => t.status === "ok" && !t.invalidated && t.evidence_ref)
    .slice(-5)
    .map((t) => {
      const env = t.evidence_ref ? s.evidence[t.evidence_ref] : undefined;
      return {
        tool_call_id: t.tool_call_id,
        name: t.name,
        evidence_ref: t.evidence_ref ?? "",
        cutoff: env?.evidence.cutoff_raw ?? "",
        summary: JSON.stringify(env?.data ?? null).slice(0, 400),
      };
    });
  const lastPatch = [...s.tools].reverse().find((t) => t.status === "ok" && t.evidence_ref);
  const filters = (lastPatch?.evidence_ref ? s.evidence[lastPatch.evidence_ref]?.evidence.filters : undefined) ?? {};
  return {
    instructions_version: "reto01-ips-v1",
    state: {
      conversation_id: s.conversation_id ?? "",
      state_version: s.state_version,
      confirmed_filters: filters,
      selected_site_keys: [],
      pending_candidates: [],
      tone_preference: s.style.source === "preference" && s.style.style === "directo" ? "concise" : "neutral",
    },
    summary: "",
    recent_turns: recent,
    tool_results: results,
    allowed_tools: ALLOWED_TOOLS,
  };
}

/**
 * Replaces the engine mid-session (docs/08 §7). The new one is seeded with the
 * neutral envelope; no tool is re-run and nothing already said is replayed.
 */
async function switchEngine(to: EngineId, reason: string, automatic: boolean): Promise<void> {
  const s = store.getState();
  if (!s.running || !s.conversation_id) return;
  if (automatic && attemptsThisTurn >= MAX_ENGINE_ATTEMPTS) {
    store.setStatus("error");
    store.pushNotice("error", "Dos intentos de motor fallaron. Sigue en modo texto o pulsa Repetir.", now());
    return;
  }
  const from = s.engine;
  const previous = engine;
  const seed = buildEnvelope();
  detach();
  engine = null;
  store.setStatus("renewing");
  void previous?.disconnect(reason);
  if (automatic) attemptsThisTurn++;
  const created = createEngine(to, deps, { script: false });
  attach(created.engine);
  try {
    await created.engine.connect({ conversationId: s.conversation_id, seed, style: s.style, voiceMode: voiceFor(to) });
  } catch {
    if (engine !== created.engine) return; // superseded by a newer action
    store.setStatus("error");
    store.pushNotice("error", `No se pudo conectar con ${engineLabel(to)}.`, now());
    return;
  }
  if (engine !== created.engine) return;
  store.setEngine(to, created.model, created.simulated);
  localEvent("session", {
    event: "switched",
    from,
    to,
    reason: automatic ? `el motor anterior se cayó: ${reason}` : "elegido en el selector",
    attempt: automatic ? attemptsThisTurn - 1 : 0,
  });
}

// ── Public controls ──────────────────────────────────────────────────────────

export async function start(opts: { question?: string; engine?: EngineId } = {}): Promise<void> {
  if (store.getState().running) {
    if (opts.question) sendText(opts.question);
    return;
  }
  const id = opts.engine ?? store.getState().engine;
  const created = createEngine(id, deps, { script: !opts.question, dropAtEnd: true });
  const conversationId = crypto.randomUUID();
  sessionStart = performance.now();
  localSeq = 0;
  firstQuery = true;
  attemptsThisTurn = 1;
  toolCache.clear();
  confirmedFilters = {};
  selectedSiteKeys = [];
  pendingQuestion = opts.question ?? null;
  store.beginSession(conversationId, id, created.model, created.simulated);
  attach(created.engine);
  pendingEcho = null;
  if (opts.question) {
    // The question is shown as soon as the greeting starts; the engine answers it after the brief.
    pendingEcho = { id: crypto.randomUUID(), text: opts.question, shown: false };
    preferDirectIfAsked(opts.question);
  }
  try {
    await created.engine.connect({ conversationId, style: store.getState().style, voiceMode: voiceFor(id) });
  } catch {
    // Cancelled by Stop/Restart while connecting: nothing to report.
  }
}

export function stop(): void {
  const previous = engine;
  detach();
  engine = null;
  pendingQuestion = null;
  pendingEcho = null;
  void previous?.disconnect("user_stop");
  store.endSession();
}

/** Cuts the agent's speech without ending the session (docs/08 §6). */
export function interruptSpeech(): void {
  engine?.interrupt(0);
}

export function sendText(text: string): void {
  const clean = text.trim();
  if (!clean) return;
  if (!store.getState().running) {
    void start({ question: clean });
    return;
  }
  if (!engine) return; // an engine switch is in flight
  preferDirectIfAsked(clean); // before sending, so it already shapes this answer
  engine.sendText(clean);
}

/** «Corregir lo que dije»: keeps the original, shows the fix, drops the old evidence (A-09). */
export function correct(utteranceId: string, text: string): void {
  const clean = text.trim();
  const s = store.getState();
  const original = s.utterances.find((u) => u.id === utteranceId);
  if (!clean || !original || !engine) return;
  const t = now();
  localEvent("transcript", {
    role: "user",
    utterance_id: crypto.randomUUID(),
    text: clean,
    final: true,
    t_start: t,
    t_end: t,
    t_source: "local",
    corrects: utteranceId,
  });
  store.invalidateTurn(original.turn_id);
  engine.sendText(`Corrección: ${clean}`);
}

/** «Más directo»: an explicit preference applies at once and persists (docs/10 §6). */
export function toggleDirect(): void {
  const s = store.getState();
  const active = s.style.source === "preference" && s.style.style === "directo";
  const decision: StyleDecision = active
    ? { style: "neutro", directives: [], reason: "Quitaste la preferencia: vuelvo al estilo por defecto.", source: "inferred", applies_from_turn: s.turns.length + 1 }
    : {
        style: "directo",
        directives: DIRECTIVES.directo,
        reason: "Lo pediste: una o dos frases, con la cifra primero.",
        source: "preference",
        applies_from_turn: s.turns.length + 1,
      };
  store.setStyle(decision);
  engine?.applyStyle(decision);
}

export function repeat(): void {
  if (store.getState().running) engine?.sendText("Repite la última respuesta, por favor.");
}

/** Clears state and transcript. Nothing is persisted anywhere (R-26). */
export function restart(): void {
  stop();
  toolCache.clear();
  store.reset();
}

export function selectEngine(id: EngineId): void {
  const s = store.getState();
  if (id === s.engine) return;
  if (s.running) void switchEngine(id, "user_choice", false);
  else {
    const info = createEngine(id, deps);
    store.setEngine(id, info.model, info.simulated);
    voiceFor(id);
  }
}

/** The cloned voice only exists for engines that support it; otherwise fall back and say so. */
function voiceFor(id: EngineId): VoiceMode {
  const mode = store.getState().voiceMode;
  if (mode === "cloned" && !store.getState().voiceModes.includes("cloned")) {
    store.setVoiceMode("engine");
    return "engine";
  }
  if (mode === "cloned" && !engineInfo(id).clonedVoice) {
    store.setVoiceMode("engine");
    store.pushNotice("info", `La voz clonada solo está disponible con OpenAI Realtime: ${engineLabel(id)} usa su propia voz.`, now());
    return "engine";
  }
  return mode;
}

/** Applies from the next session or engine switch (the voice is fixed when the credential is issued). */
export function setVoiceMode(mode: VoiceMode): void {
  const s = store.getState();
  if (mode === "cloned" && (!engineInfo(s.engine).clonedVoice || !s.voiceModes.includes("cloned"))) return;
  store.setVoiceMode(mode);
  if (s.running) store.pushNotice("info", "El cambio de voz aplica al iniciar la próxima sesión.", now());
}

export function setVoiceAnalysis(on: boolean): void {
  store.setVoiceAnalysis(on);
}

/** «Reconsultar»: repeats the call live and checks that the result matches (A-24). */
export async function requery(toolCallId: string): Promise<void> {
  const s = store.getState();
  const entry = s.tools.find((t) => t.tool_call_id === toolCallId);
  if (!entry || entry.requery?.pending) return;
  const before = entry.evidence_ref ? s.evidence[entry.evidence_ref] : undefined;
  store.setRequery(toolCallId, { pending: true });
  const env = await runTool(
    { tool_call_id: crypto.randomUUID(), name: entry.name, args: entry.args },
    canonicalContext({ conversation_id: s.conversation_id ?? "", turn_id: entry.turn_id ?? "", state_version: entry.state_version }),
    { forceLive: true },
  );
  const matches = env.status === "ok" && before !== undefined && JSON.stringify(env.data) === JSON.stringify(before.data);
  store.setRequery(toolCallId, { pending: false, matches, ms: env.trace.ms, at: Date.now() });
}

// Ask the backend which voices it offers, so the UI only shows what exists (docs/08 §3).
void fetchVoiceModes().then((modes) => store.setVoiceModes(modes));

// Initial engine metadata, so the HUD is truthful before the first session.
{
  const info = createEngine(store.getState().engine, deps);
  store.setEngine(store.getState().engine, info.model, info.simulated);
}
