/**
 * Plausibility of a user transcript: noise that the speech recognizer turned
 * into text must not become a question (ambient-noise fix).
 */
import { describe, expect, it } from "vitest";
import { isPlausiblePartial, isPlausibleUserSpeech, isSettledPartial, mayBeSpeech } from "../../src/voice/transcript-filter";

describe("isPlausibleUserSpeech", () => {
  it.each([
    "",
    "   ",
    "公主。",
    "公主",
    "ご視聴ありがとうございました",
    "시청해 주셔서 감사합니다",
    "Спасибо за просмотр",
    "شكرا",
    "תודה",
    "ขอบคุณ",
    "धन्यवाद",
    "Hola 公主",
    "Gracias.",
    "gracias",
    "¡Muchas gracias!",
    "Gracias por ver el video.",
    "GRACIAS POR VER EL VÍDEO",
    "Subtítulos realizados por la comunidad de Amara.org",
    "Suscríbete",
    "¡Suscríbete al canal!",
    "Música",
    "[Música]",
    "[Aplausos]",
    "...",
    "…",
    "¿?",
    "Mm.",
    "mmm",
    "Hmm",
    "Eh.",
    "Ah",
    "a",
    "1234",
  ])("rejects %j", (text) => {
    expect(isPlausibleUserSpeech(text)).toBe(false);
  });

  it.each([
    "¿Cuántas IPS hay en Cali?",
    "sí",
    "Sí.",
    "si",
    "no",
    "No.",
    "ok",
    "Vale",
    "claro",
    "listo",
    "dale",
    "correcto",
    "exacto",
    "Melgar",
    "Cali",
    "Bogotá",
    "Medellín",
    "gracias, eso es todo",
    "Muchas gracias por la información",
    "¿Y en Ibagué?",
    "Compara Cali y Medellín",
    "Mi cédula es 1234567",
  ])("accepts %j", (text) => {
    expect(isPlausibleUserSpeech(text)).toBe(true);
  });
});

describe("partials", () => {
  it("a partial bubble needs a Latin word and no foreign script", () => {
    expect(isPlausiblePartial("公主")).toBe(false);
    expect(isPlausiblePartial("y")).toBe(false);
    expect(isPlausiblePartial("¿Cuán")).toBe(true);
    expect(isPlausiblePartial("sí")).toBe(true);
  });

  it("an answer is released early only for a clear question, never for the start of a hallucination", () => {
    expect(isSettledPartial("¿Cuántas IPS")).toBe(true);
    expect(isSettledPartial("Cali")).toBe(false);
    expect(isSettledPartial("Gracias por")).toBe(false);
    expect(isSettledPartial("Gracias por ver el video")).toBe(false);
    expect(isSettledPartial("公主 公主")).toBe(false);
  });

  it("a loose fragment may begin speech only with a Latin letter", () => {
    expect(mayBeSpeech("公主")).toBe(false);
    expect(mayBeSpeech(" Y")).toBe(true);
  });
});
