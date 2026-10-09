/**
 * Plausibility of a user transcript (ambient-noise fix).
 *
 * The providers' speech recognizers invent text on segments of pure noise or
 * silence that their VAD committed as a turn: «公主。», «Gracias por ver el
 * video.», «Subtítulos realizados por la comunidad de Amara.org». A text that
 * fails these checks is not a question: it is not shown, not answered and not
 * analysed. Pure functions, no state: the engine core decides what to do.
 */

/** Scripts that never belong to an es-CO conversation: their presence marks a hallucination. */
const FOREIGN_SCRIPT =
  /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\p{Script=Cyrillic}\p{Script=Arabic}\p{Script=Hebrew}\p{Script=Thai}\p{Script=Devanagari}]/u;
const LETTER = /\p{L}/gu;
const LATIN_LETTER = /\p{Script=Latin}/gu;
const LATIN_WORD = /\p{Script=Latin}{2,}/u;
/** Minimum share of Latin letters (á é í ó ú ü ñ included) among all letters. */
const MIN_LATIN_SHARE = 0.8;

/**
 * Whole texts that speech recognizers produce on silence or noise (normalized:
 * lower case, no accents, punctuation as spaces). Matched against the whole
 * transcript, never as a substring, so «gracias, eso es todo» stays valid.
 */
const HALLUCINATIONS = [
  "gracias",
  "muchas gracias",
  "gracias por ver",
  "gracias por ver el video",
  "muchas gracias por ver el video",
  "subtitulos realizados por la comunidad de amara org",
  "subtitulos por la comunidad de amara org",
  "suscribete",
  "suscribete al canal",
  "musica",
  "aplausos",
].map(normalize);

/** Interjections and hums with no content: «mm», «mmm», «hmm», «eh», «ah», «uh», «um». */
const FILLER = /^(?:h?m+|e+h+|a+h+|u+h+|u+m+)$/;

/** Lower case, accents removed, anything that is not a letter or a digit as a single space. */
export function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function scriptLooksSpanish(text: string): boolean {
  if (FOREIGN_SCRIPT.test(text)) return false;
  const letters = text.match(LETTER)?.length ?? 0;
  if (letters < 2) return false;
  const latin = text.match(LATIN_LETTER)?.length ?? 0;
  return latin / letters >= MIN_LATIN_SHARE;
}

/** True when the normalized text is a known silence hallucination or a content-free filler. */
function isHallucination(norm: string): boolean {
  return HALLUCINATIONS.includes(norm) || norm.includes("amara org") || FILLER.test(norm.replace(/\s+/g, ""));
}

/**
 * Final user transcript: false when it is empty, has fewer than two letters, is
 * written (even partly) in a non-Latin script, or is one of the phrases speech
 * recognizers invent on silence. Short real answers («sí», «no», «Melgar») pass.
 */
export function isPlausibleUserSpeech(text: string): boolean {
  if (!text || !text.trim()) return false;
  if (!scriptLooksSpanish(text)) return false;
  return !isHallucination(normalize(text));
}

/**
 * Partial user transcript: shown only once it holds at least one Latin word and
 * nothing in a foreign script, so «公主» never flashes on screen.
 */
export function isPlausiblePartial(text: string): boolean {
  return LATIN_WORD.test(text) && scriptLooksSpanish(text);
}

/**
 * A loose transcript fragment that may begin a real utterance: at least one Latin
 * letter and nothing in a foreign script. Used before any word is complete.
 */
export function mayBeSpeech(text: string): boolean {
  return /\p{Script=Latin}/u.test(text) && !FOREIGN_SCRIPT.test(text);
}

/**
 * A partial that is already clearly a question: two or more words, plausible,
 * and not the beginning of a known hallucination («gracias por…»). The answer to
 * it can be released before the final transcript arrives.
 */
export function isSettledPartial(text: string): boolean {
  const norm = normalize(text);
  if (norm.split(" ").filter(Boolean).length < 2) return false;
  if (!isPlausibleUserSpeech(text)) return false;
  return !HALLUCINATIONS.some((h) => h.startsWith(norm));
}
