/**
 * Conversation controller: owns the active VoiceEngine and wires it to the store.
 *
 * It is the only module that talks to both. Panels call these functions; they
 * never touch an engine. Responsibilities (docs/08 §5–§7, docs/10 §5–§6):
 * tool bridge with idempotency, engine switch with a neutral context envelope,
 * analyst calls, style decisions and the user controls.
 */
import { analyze, DIRECTIVES, inferStyle } from "./analyst";
import { fetchBrief, runTool, type ToolContext } from "./api";
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
const toolCache = new Map<string, Promise<EvidenceEnvelope>>();

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
    const result = runTool(call, ctx, { forceLive }).then((env) => {
      store.putEvidence(env);
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
      const event = ev as AnyEngineEvent;
      store.dispatch(event);
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
      void runAnalysis(p.utterance_id, p.text, ev.turn_id, ev.state_version, p.t_start);
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

async function runAnalysis(utterance_id: string, text: string, turn_id: string, state_version: number, t: number): Promise<void> {
  const conversation = store.getState().conversation_id;
  const entry = await analyze({ utterance_id, text, turn_id, state_version, t, voiceConsent: store.getState().voiceAnalysis });
  const s = store.getState();
  if (s.conversation_id !== conversation) return; // the session was restarted meanwhile
  store.pushAffect(entry);
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
    await created.engine.connect({ conversationId: s.conversation_id, seed, style: s.style, voice: voiceFor(to) });
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
  pendingQuestion = opts.question ?? null;
  store.beginSession(conversationId, id, created.model, created.simulated);
  attach(created.engine);
  try {
    await created.engine.connect({ conversationId, style: store.getState().style, voice: voiceFor(id) });
  } catch {
    // Cancelled by Stop/Restart while connecting: nothing to report.
  }
}

export function stop(): void {
  const previous = engine;
  detach();
  engine = null;
  pendingQuestion = null;
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
  if (mode === "cloned" && !engineInfo(s.engine).clonedVoice) return;
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
    { conversation_id: s.conversation_id ?? "", turn_id: entry.turn_id ?? "", state_version: entry.state_version },
    { forceLive: true },
  );
  const matches = env.status === "ok" && before !== undefined && JSON.stringify(env.data) === JSON.stringify(before.data);
  store.setRequery(toolCallId, { pending: false, matches, ms: env.trace.ms, at: Date.now() });
}

// Initial engine metadata, so the HUD is truthful before the first session.
{
  const info = createEngine(store.getState().engine, deps);
  store.setEngine(store.getState().engine, info.model, info.simulated);
}
