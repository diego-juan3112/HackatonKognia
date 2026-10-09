/**
 * Explicit voice consent (docs/10 §6, R-26).
 *
 * The microphone is not opened and no audio clip is sent to `/analysis/utterance`
 * until the person presses «Usar mi voz». Until then the console is text only and
 * every analysis goes out with `voice_consent: false`. The choice is remembered
 * only for this tab (sessionStorage) and can be withdrawn at any time.
 *
 * The store starts every conversation with `voiceAnalysis: false` and `reset()`
 * returns to that, so this module re-applies the person's choice whenever the
 * store disagrees with it.
 */
import * as controller from "../voice/controller";
import { getState, subscribe } from "../voice/store";

export const CONSENT_KEY = "ips.voice-consent";

/** Reads the remembered consent; anything but an explicit "on" means no consent. */
export function readConsent(storage: Pick<Storage, "getItem"> | null | undefined): boolean {
  try {
    return storage?.getItem(CONSENT_KEY) === "on";
  } catch {
    return false;
  }
}

export function writeConsent(storage: Pick<Storage, "setItem" | "removeItem"> | null | undefined, on: boolean): void {
  try {
    if (on) storage?.setItem(CONSENT_KEY, "on");
    else storage?.removeItem(CONSENT_KEY);
  } catch {
    // Private mode or blocked storage: the choice lasts for this page only.
  }
}

function session(): Storage | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

let wanted = readConsent(session());
let started = false;

const apply = (): void => {
  if (getState().voiceAnalysis !== wanted) controller.setVoiceAnalysis(wanted);
};

/** Idempotent: called once from the layout. */
export function keepAnalysisDefault(): void {
  if (started) return;
  started = true;
  subscribe((_state, slices) => {
    if (slices.has("reset") || slices.has("meta")) apply();
  });
  apply();
}

export function analysisWanted(): boolean {
  return wanted;
}

/** «Usar mi voz» (true) or «Dejar de usar mi voz» (false). */
export function setAnalysisWanted(on: boolean): void {
  wanted = on;
  writeConsent(session(), on);
  apply();
}
