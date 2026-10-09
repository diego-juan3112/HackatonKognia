/**
 * Voice analysis is on by default: there is no consent step, only a switch on
 * the admin board to turn it off.
 *
 * The store starts every conversation with `voiceAnalysis: false` and `reset()`
 * returns to that, so this module re-applies the operator's choice whenever the
 * store disagrees with it. The choice lives in localStorage so an explicit
 * "off" survives a reload.
 */
import * as controller from "../voice/controller";
import { getState, subscribe } from "../voice/store";

const KEY = "ips.voice-analysis";

function read(): boolean {
  try {
    return localStorage.getItem(KEY) !== "off";
  } catch {
    return true;
  }
}

let wanted = read();
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

export function setAnalysisWanted(on: boolean): void {
  wanted = on;
  try {
    localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    // Private mode: the choice lasts for this page only.
  }
  apply();
}
