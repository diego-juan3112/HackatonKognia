/**
 * Client side of the analyst (docs/10 §6).
 *
 * With a backend: `POST /analysis/utterance`. Without one: scripted readings from
 * web/mocks/affect.json, fused here with the deterministic rule of docs/10
 * («Fusión»). A failed analysis is always "uncertain", never a stale label.
 */
import affectMocks from "../../mocks/affect.json";
import { apiFetch, USING_MOCKS } from "./api";
import type { AffectEntry } from "./store";
import type { AffectEstimate, Emotion, Sentiment, StateHint, StyleDecision, StyleId } from "./types";

interface Reading {
  sentiment: Sentiment;
  emotion: Emotion;
  state_hint: StateHint;
  cues: string[];
}

type MockKey = Exclude<keyof typeof affectMocks, "_note">;

const fold = (s: string): string =>
  s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

function mockKey(text: string): MockKey {
  const q = fold(text);
  if (/^no,|dije|correccion/.test(q)) return "fix_melgar";
  if (/confund|directo|breve/.test(q)) return "ask_direct";
  if (/gracias/.test(q)) return "thanks";
  if (/municipios/.test(q)) return "q_top_beds";
  if (/medellin/.test(q)) return "q_beds_medellin";
  return "default";
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

export interface AnalyzeInput {
  utterance_id: string;
  text: string;
  turn_id: string;
  state_version: number;
  t: number;
  /** Voice analysis only runs with consent (R-26); the audio clip is sent only then. */
  voiceConsent: boolean;
  /** Session-clock bounds of the utterance. */
  t_start?: number;
  t_end?: number;
  /** Observable facts about the turn (e.g. it interrupted the agent, it was a correction). */
  signals?: Record<string, unknown>;
  /** WAV clip of the utterance, base64. Only with consent; never stored. */
  audioWavB64?: string | null;
  /** Up to 3 previous estimates: the backend keeps no state. */
  affectHistory?: AffectEstimate[];
  tonePreference?: string;
  currentStyle?: StyleDecision;
  turnIndex?: number;
}

type ChannelReading = Pick<AffectEstimate, "sentiment" | "emotion" | "state_hint">;

function channel(v: unknown): ChannelReading | undefined {
  if (!v || typeof v !== "object") return undefined;
  const r = v as Partial<ChannelReading>;
  return r.sentiment && r.emotion && r.state_hint ? { sentiment: r.sentiment, emotion: r.emotion, state_hint: r.state_hint } : undefined;
}

function styleFrom(v: unknown, turnIndex: number): StyleDecision | undefined {
  if (!v || typeof v !== "object") return undefined;
  const s = v as Partial<StyleDecision>;
  if (!s.style || !(s.style in DIRECTIVES)) return undefined;
  return {
    style: s.style,
    directives: Array.isArray(s.directives) ? s.directives.filter((d): d is string => typeof d === "string") : DIRECTIVES[s.style],
    reason: typeof s.reason === "string" ? s.reason : "",
    source: s.source === "preference" ? "preference" : "inferred",
    applies_from_turn: typeof s.applies_from_turn === "number" ? s.applies_from_turn : turnIndex + 1,
  };
}

function uncertain(input: AnalyzeInput, ms: number | null): AffectEntry {
  return {
    utterance_id: input.utterance_id,
    text: input.text,
    t: input.t,
    analysis_ms: ms,
    estimate: {
      turn_id: input.turn_id,
      state_version: input.state_version,
      observed_at: new Date().toISOString(),
      sentiment: "uncertain",
      emotion: "incierta",
      state_hint: "desconocido",
      method: "text",
      discrepancy: false,
      cues: [],
      confidence: null,
    },
  };
}

export async function analyze(input: AnalyzeInput): Promise<AffectEntry> {
  if (!USING_MOCKS) return analyzeRemote(input);
  const mock = affectMocks[mockKey(input.text)];
  await sleep(mock.analysis_ms);
  const text = mock.text as Reading;
  const voice = input.voiceConsent ? (mock.voice as Reading) : null;
  const agree = !voice || (voice.sentiment === text.sentiment && voice.emotion === text.emotion);
  // Deterministic fusion: equal labels pass through; a disagreement is shown, not hidden.
  // When they disagree the acoustic reading leads, because tone carries what words omit.
  const lead = voice && !agree ? voice : text;
  const pick = ({ sentiment, emotion, state_hint }: Reading) => ({ sentiment, emotion, state_hint });
  return {
    utterance_id: input.utterance_id,
    text: input.text,
    t: input.t,
    analysis_ms: mock.analysis_ms,
    channels: voice ? { text: pick(text), voice: pick(voice) } : { text: pick(text) },
    estimate: {
      turn_id: input.turn_id,
      state_version: input.state_version,
      observed_at: new Date().toISOString(),
      sentiment: lead.sentiment,
      emotion: lead.emotion,
      state_hint: lead.state_hint,
      method: voice ? "fused" : "text",
      discrepancy: !agree,
      cues: voice ? [...new Set([...text.cues, ...voice.cues])] : text.cues,
      confidence: null,
    },
  };
}

/**
 * `POST /analysis/utterance` (JSON). The backend is stateless, so the history, the
 * tone preference and the style in force travel with each call. It answers the
 * fused estimate, the per-channel readings and the style for the next turn.
 */
async function analyzeRemote(input: AnalyzeInput): Promise<AffectEntry> {
  const started = performance.now();
  const turnIndex = input.turnIndex ?? 1;
  try {
    const body: Record<string, unknown> = {
      turn_id: input.turn_id,
      state_version: input.state_version,
      text: input.text,
      t_start: input.t_start ?? input.t,
      t_end: input.t_end ?? input.t,
      signals: input.signals ?? {},
      voice_consent: input.voiceConsent,
      affect_history: (input.affectHistory ?? []).slice(-3),
      tone_preference: input.tonePreference ?? "neutral",
      current_style: input.currentStyle ?? null,
      turn_index: turnIndex,
    };
    if (input.voiceConsent && input.audioWavB64) body.audio_wav_b64 = input.audioWavB64;
    const res = await apiFetch("/analysis/utterance", { method: "POST", body: JSON.stringify(body) }, 5000);
    if (!res.ok) throw new Error(String(res.status));
    const parsed = (await res.json()) as { affect?: Record<string, unknown>; style?: unknown } & Record<string, unknown>;
    const raw = (parsed.affect ?? parsed) as Record<string, unknown>;
    const estimate = raw as unknown as AffectEstimate;
    if (!estimate.sentiment) throw new Error("bad shape");
    const text = channel(raw.text_estimate);
    const voice = channel(raw.voice_estimate);
    return {
      utterance_id: input.utterance_id,
      text: input.text,
      t: input.t,
      estimate,
      channels: text || voice ? { ...(text ? { text } : {}), ...(voice ? { voice } : {}) } : undefined,
      style: styleFrom(parsed.style, turnIndex),
      analysis_ms: Math.round(performance.now() - started),
    };
  } catch {
    return uncertain(input, null);
  }
}

// ── Style policy (client mirror of config/style_policy.yaml for the mock path) ─

const STYLE_FOR_HINT: Partial<Record<StateHint, { style: StyleId; reason: string }>> = {
  frustración: { style: "directo", reason: "Parece frustrado: respuestas más breves y al grano" },
  confusión: { style: "didactico", reason: "Parece confundido: explico paso a paso" },
  prisa: { style: "directo", reason: "Parece tener prisa: respuestas más breves" },
};

export const DIRECTIVES: Record<StyleId, string[]> = {
  directo: ["Responde en una o dos frases.", "Da primero la cifra.", "Sin rodeos."],
  calido: ["Reconoce brevemente lo que siente la persona.", "Tono cercano y paciente."],
  didactico: ["Explica paso a paso con un ejemplo corto.", "Define IPS, sede y capacidad instalada."],
  neutro: [],
};

export const MIN_CONSECUTIVE_SIGNALS = 2;

export interface StyleOutcome {
  decision: StyleDecision | null;
  signal: { hint: string; count: number; needed: number } | null;
}

/**
 * An inferred style needs two consecutive signals (it must not oscillate); an
 * explicit preference is handled by the caller and always wins.
 */
export function inferStyle(history: AffectEstimate[], current: StyleDecision, nextTurn: number): StyleOutcome {
  if (current.source === "preference") return { decision: null, signal: null };
  const last = history[history.length - 1];
  const target = last ? STYLE_FOR_HINT[last.state_hint] : undefined;
  if (!last || !target || target.style === current.style) return { decision: null, signal: null };
  let count = 0;
  for (let i = history.length - 1; i >= 0; i--) {
    const h = history[i];
    if (h && STYLE_FOR_HINT[h.state_hint]?.style === target.style) count++;
    else break;
  }
  if (count < MIN_CONSECUTIVE_SIGNALS) return { decision: null, signal: { hint: last.state_hint, count, needed: MIN_CONSECUTIVE_SIGNALS } };
  return {
    decision: { style: target.style, directives: DIRECTIVES[target.style], reason: target.reason, source: "inferred", applies_from_turn: nextTurn },
    signal: null,
  };
}
