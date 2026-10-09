/**
 * Analyst and style policy (docs/10 §6; A-14, A-21, A-22): estimates are always
 * estimates, voice needs consent, and an inferred style must not oscillate.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { analyze, inferStyle, MIN_CONSECUTIVE_SIGNALS } from "../../src/voice/analyst";
import { NEUTRAL_STYLE } from "../../src/voice/store";
import type { AffectEstimate, StateHint, StyleDecision } from "../../src/voice/types";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

async function run(text: string, voiceConsent: boolean) {
  const p = analyze({ utterance_id: "u1", text, turn_id: "t1", state_version: 1, t: 0, voiceConsent });
  await vi.advanceTimersByTimeAsync(5_000);
  return p;
}

const est = (state_hint: StateHint): AffectEstimate => ({
  turn_id: "t",
  state_version: 1,
  observed_at: "",
  sentiment: "neutral",
  emotion: "neutral",
  state_hint,
  method: "text",
  discrepancy: false,
  cues: [],
  confidence: null,
});

describe("analista simulado", () => {
  it("sin consentimiento solo usa el texto (R-26, A-25)", async () => {
    const e = await run("No, dije Melgar.", false);
    expect(e.estimate.method).toBe("text");
    expect(e.channels?.voice).toBeUndefined();
    expect(e.estimate.discrepancy).toBe(false);
  });

  it("con consentimiento la voz puede discrepar del texto y se marca (A-21)", async () => {
    const e = await run("No, dije Melgar.", true);
    expect(e.estimate.method).toBe("fused");
    expect(e.estimate.discrepancy).toBe(true);
    expect(e.channels?.text?.sentiment).toBe("neutral");
    expect(e.channels?.voice?.sentiment).toBe("negative");
    expect(e.estimate.state_hint).toBe("frustración");
  });

  it("nunca publica una confianza calibrada", async () => {
    for (const consent of [false, true]) {
      const e = await run("¿Qué municipios tienen más camas?", consent);
      expect(e.estimate.confidence).toBeNull();
    }
  });

  it("«me estás confundiendo, sé más directo» se lee como frustración (A-14)", async () => {
    const e = await run("Me estás confundiendo, sé más directo", false);
    expect(e.estimate).toMatchObject({ sentiment: "negative", state_hint: "frustración" });
    expect(e.estimate.cues.length).toBeGreaterThan(0);
  });
});

describe("política de estilo", () => {
  it("una sola señal no cambia el estilo: informa el avance", () => {
    const out = inferStyle([est("interés"), est("frustración")], NEUTRAL_STYLE, 3);
    expect(out.decision).toBeNull();
    expect(out.signal).toEqual({ hint: "frustración", count: 1, needed: MIN_CONSECUTIVE_SIGNALS });
  });

  it("dos señales seguidas cambian a directo con motivo y desde el turno siguiente (A-22)", () => {
    const out = inferStyle([est("frustración"), est("frustración")], NEUTRAL_STYLE, 4);
    expect(out.decision).toMatchObject({ style: "directo", source: "inferred", applies_from_turn: 4 });
    expect(out.decision!.reason.length).toBeGreaterThan(10);
    expect(out.decision!.directives.length).toBeGreaterThan(0);
  });

  it("la confusión lleva a didáctico", () => {
    expect(inferStyle([est("confusión"), est("confusión")], NEUTRAL_STYLE, 3).decision?.style).toBe("didactico");
  });

  it("la preferencia explícita persiste y gana a lo inferido (A-22)", () => {
    const pref: StyleDecision = { style: "directo", directives: [], reason: "Lo pediste", source: "preference", applies_from_turn: 2 };
    expect(inferStyle([est("confusión"), est("confusión"), est("confusión")], pref, 5)).toEqual({ decision: null, signal: null });
  });

  it("señales que no piden cambio no hacen nada", () => {
    expect(inferStyle([est("interés"), est("satisfacción")], NEUTRAL_STYLE, 3)).toEqual({ decision: null, signal: null });
  });
});
