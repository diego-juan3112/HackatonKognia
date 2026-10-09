/**
 * Engine factory: the single place where a VoiceEngine implementation is chosen.
 *
 * With a backend (`PUBLIC_API_URL`), each engine id resolves to its real adapter:
 * `./openai-engine.ts` and `./gemini-engine.ts`. They ask `POST /realtime/session`
 * for an ephemeral credential, open the provider WebSocket from the browser and
 * share one audio stack (`./audio/`). No provider key reaches the browser (R-28).
 *
 * Without a backend, or when the double is forced, every id resolves to FakeEngine
 * (scripted, no audio, no network) and the UI says so. The double is forced with
 * `PUBLIC_VOICE_ENGINE=fake` at build time or `?engine=fake` in the URL.
 *
 * Nothing else in the UI changes: the controller, the store and every panel only
 * know VoiceEngine (docs/08 §2).
 */
import { USING_MOCKS } from "./api";
import { FakeEngine, type EngineDeps, type FakeEngineOptions } from "./fake-engine";
import { GeminiLiveEngine } from "./gemini-engine";
import { OpenAIRealtimeEngine } from "./openai-engine";
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

const REAL_ENGINES: Record<EngineId, RealEngineCtor> = { openai: OpenAIRealtimeEngine, gemini: GeminiLiveEngine };

function fakeForced(): boolean {
  if ((import.meta.env.PUBLIC_VOICE_ENGINE ?? "") === "fake") return true;
  try {
    return typeof location !== "undefined" && new URLSearchParams(location.search).get("engine") === "fake";
  } catch {
    return false;
  }
}

/** True when sessions run on the real engines (there is a backend and the double is not forced). */
export const realEngines = (): boolean => !USING_MOCKS && !fakeForced();

export function createEngine(id: EngineId, deps: EngineDeps, fake: FakeEngineOptions = {}): CreatedEngine {
  if (realEngines()) {
    const Real = REAL_ENGINES[id];
    return { engine: new Real(deps), model: engineInfo(id).model, simulated: false };
  }
  // The label names the model the real adapter will use, and says plainly that this is the double.
  return { engine: new FakeEngine(id, deps, fake), model: `${engineInfo(id).model} (guion simulado)`, simulated: true };
}
