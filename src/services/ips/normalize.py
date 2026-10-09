"""Name normalisation shared by the lexicon and its builder (docs/09 section 7)."""

from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
# Spoken and written forms of the same thing collapse to one token.
_SYNONYMS = (
    (re.compile(r"\bempresa social del estado\b"), "ese"),
    (re.compile(r"\be s e\b"), "ese"),
    (re.compile(r"\bi p s\b"), "ips"),
    (re.compile(r"\bd c\b"), "dc"),
)


def norm(text: str) -> str:
    """Lower-case, strip accents and punctuation: 'E.S.E. Hospital San José' -> 'ese hospital san jose'."""
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = _SPACES.sub(" ", _PUNCT.sub(" ", s)).strip()
    for pattern, repl in _SYNONYMS:
        s = pattern.sub(repl, s)
    return s
