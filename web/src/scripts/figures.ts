/**
 * Marks figures that the backend could not find in the evidence of the turn
 * (`POST /verify/answer` → `unsupported`). Works on text that was already escaped:
 * digits, dots and commas are not touched by esc().
 */

/** "97.036" → 97036, "1.234,5" → 1234.5, "12,5" → 12.5, "1234" → 1234. */
export function parseSpokenNumber(token: string): number | null {
  let t = token.replace(/[.,]+$/, "");
  if (!/\d/.test(t)) return null;
  // Thousands with dots (es-CO), decimal comma.
  if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(t)) t = t.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(t)) t = t.replace(/,/g, "");
  else t = t.replace(",", ".");
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

/** Wraps every figure of `escaped` whose value is in `unsupported` with a «no verificada» mark. */
export function markFigures(escaped: string, unsupported: readonly number[] | undefined): string {
  if (!unsupported || unsupported.length === 0) return escaped;
  const wanted = new Set(unsupported.map(Number));
  return escaped.replace(/\d[\d.,]*\d|\d/g, (token) => {
    const n = parseSpokenNumber(token);
    return n !== null && wanted.has(n) ? `<mark class="unverified" title="Cifra no verificada">${token}</mark>` : token;
  });
}
