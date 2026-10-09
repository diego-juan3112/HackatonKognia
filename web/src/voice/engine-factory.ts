/**
 * Engine factory: the single place where a VoiceEngine implementation is chosen.
 *
 * TODAY every engine id resolves to FakeEngine (scripted, no audio, no network).
 *
 * HOW TO PLUG THE REAL ENGINES (docs/08 §2–§4):
 *
 *   1. Create `./openai-engine.ts` exporting `class OpenAIRealtimeEngine implements VoiceEngine`
 *      and `./gemini-engine.ts` exporting `class GeminiLiveEngine implements VoiceEngine`.
 *      Each adapter:
 *        - in `connect()`, calls `POST {PUBLIC_API_URL}/realtime/session` with
 *          `{ engine, conversation_id, seed?, style?, locale: "es-CO" }` and opens the
 *          provider WebSocket with the ephemeral credential it returns (`connect.url`,
 *          `connect.token`). No provider key ever reaches the browser (R-28);
 *        - translates provider messages into the EngineEvents of `./types.ts`. No provider
 *          event name, audio format or credential leaves the adapter (R-03);
 *        - on a provider function call, emits `tool_call`, awaits `deps.runTool(...)`,
 *          emits `tool_result` and hands `{status, data, warnings, evidence_summary}` back
 *          to the provider as the function output;
 *        - shares the one audio stack (MicTap + Player, docs/08 §4), to be added under
 *          `./audio/`.
 *   2. Register them in REAL_ENGINES below. Nothing else in the UI changes: the
 *      controller (`./controller.ts`), the store and every panel only know VoiceEngine.
 *   3. `model` below comes from the voice spike; an adapter should overwrite it with the
 *      `model` field of `POST /realtime/session` once connected.
 */
import { FakeEngine, type EngineDeps, type FakeEngineOptions } from "./fake-engine";
import type { EngineId, VoiceEngine } from "./types";

export interface EngineInfo {
  id: EngineId;
  label: string;
  /** Model id chosen in the voice spike (G2). */
  model: string;
  /** The cloned voice (Cartesia) is only wired for this engine. */
  clonedVoice: boolean;
}

export const ENGINES: readonly EngineInfo[] = [
  { id: "openai", label: "OpenAI Realtime", model: "gpt-realtime-2.1", clonedVoice: true },
  { id: "gemini", label: "Gemini Live", model: "gemini-3.8-live", clonedVoice: false },
];

export const engineLabel = (id: EngineId): string => ENGINES.find((e) => e.id === id)?.label ?? id;

export const engineInfo = (id: EngineId): EngineInfo => ENGINES.find((e) => e.id === id) ?? ENGINES[0]!;

export const otherEngine = (id: EngineId): EngineId => (id === "openai" ? "gemini" : "openai");

export interface CreatedEngine {
  engine: VoiceEngine;
  /** Model id shown in the HUD. */
  model: string;
  /** True while the engine is the scripted double; the UI says so. */
  simulated: boolean;
}

type RealEngineCtor = new (deps: EngineDeps) => VoiceEngine;

/**
 * Real adapters go here, e.g.:
 *   import { OpenAIRealtimeEngine } from "./openai-engine";
 *   import { GeminiLiveEngine } from "./gemini-engine";
 *   const REAL_ENGINES = { openai: OpenAIRealtimeEngine, gemini: GeminiLiveEngine };
 */
const REAL_ENGINES: Partial<Record<EngineId, RealEngineCtor>> = {};

export function createEngine(id: EngineId, deps: EngineDeps, fake: FakeEngineOptions = {}): CreatedEngine {
  const Real = REAL_ENGINES[id];
  if (Real) {
    return { engine: new Real(deps), model: engineInfo(id).model, simulated: false };
  }
  // The label names the model the real adapter will use, and says plainly that this is the double.
  return { engine: new FakeEngine(id, deps, fake), model: `${engineInfo(id).model} (guion simulado)`, simulated: true };
}
