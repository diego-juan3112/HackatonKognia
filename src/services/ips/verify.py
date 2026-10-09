"""Figure verifier (docs/10 section 1, "Verificador de cifras"): deterministic, no LLM.

Checks that every number the agent said appears in the evidence of that turn
(R-22). The browser sends the agent's text and the tool results it already
holds; the server keeps nothing. A number not backed by evidence is flagged so
the UI can mark it «cifra no verificada» -- it never rewrites the answer.

Limits (stated, not hidden): numbers spelled out in words are not parsed, and
small numbers (< 10), the cutoff year 2022 and the day 5 are ignored because
they appear in ordinary speech ("tres resultados", "noviembre de 2022").
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.\s ]\d{3})+|\d+)(?:,(\d+))?(?![\w])")
_IGNORED = {2022, 5}
_DIGITS = re.compile(r"\d+")


def numbers_in_text(text: str) -> list[int | float]:
    found: list[int | float] = []
    for m in _NUM.finditer(text):
        whole = int(re.sub(r"[.\s ]", "", m.group(1)))
        value: int | float = float(f"{whole}.{m.group(2)}") if m.group(2) else whole
        if value < 10 or value in _IGNORED:
            continue
        found.append(value)
    return found


def numbers_in_evidence(obj: Any) -> set[float]:
    """Every number anywhere in the tool results: numeric fields AND digit runs inside text.

    Text matters: phones («2669633-3104474985»), addresses («CALLE 2 SUR 46-116»), codes
    and names come from the source as strings. Ignoring them made the verifier flag a
    correctly read phone number as an invented figure (bug seen in a live test, 2026-10-09).
    """
    out: set[float] = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int | float):
        out.add(float(obj))
    elif isinstance(obj, str):
        for run in _DIGITS.findall(obj):
            out.add(float(run))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("tool_call_id", "query_fingerprint"):
                continue
            out |= numbers_in_evidence(v)
    elif isinstance(obj, list | tuple):
        for v in obj:
            out |= numbers_in_evidence(v)
    return out


def verify(text: str, evidence_data: Iterable[Any]) -> dict[str, Any]:
    said = numbers_in_text(text)
    known = set()
    for d in evidence_data:
        known |= numbers_in_evidence(d)
    unsupported = [n for n in said if float(n) not in known]
    correction = None
    if unsupported:
        # Self-correction within the conversation (docs/10 section 5, "Recuperar no es aprender"):
        # the browser hands this note to the engine, which corrects itself on the next turn.
        listed = ", ".join(_fmt(n) for n in unsupported)
        correction = (
            "[Nota del sistema — verificación de cifras; no es una pregunta de la persona] "
            f"En tu última respuesta dijiste {listed}, que no aparece en los resultados de herramientas de este turno. "
            "Corrígete ahora en una frase, con sencillez: da la cifra exacta del resultado o di que ese dato no lo "
            "tienes. No repitas la cifra no verificada."
        )
    return {"grounded": not unsupported, "numbers": said, "unsupported": unsupported,
            "checked": len(said), "correction": correction,
            "note": "Los números escritos en palabras no se verifican."}


def _fmt(n: int | float) -> str:
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else str(n).replace(".", ",")
