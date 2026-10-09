"""Entity resolution against data/lexicon.json (docs/09 section 7).

The lexicon only normalises names and proposes candidates; **it is never a
source of figures** (R-22). Policy:

- exact match after normalisation -> ok;
- a unique prefix or a single very close fuzzy match -> ok + ``FILTER_NORMALIZED``;
- several plausible values -> ``ambiguous`` with <= 3 candidates (never pick the first);
- a homonym municipality without department -> ``ambiguous`` (A-04);
- districts listed as departments (Cali, Barranquilla...) -> resolved with a
  ``DISTRICT_AS_DEPARTMENT`` warning (A-26).
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from services.ips.normalize import norm

# District -> the department that geographically contains it (docs/09 section 9, trap 1).
DISTRICTS: dict[str, str] = {
    "Barranquilla": "Atlántico",
    "Buenaventura": "Valle del cauca",
    "Cali": "Valle del cauca",
    "Cartagena": "Bolívar",
    "Santa Marta": "Magdalena",
}
_ALIASES = {"bogota": "bogota dc", "valle": "valle del cauca", "san andres": "san andres y providencia",
            "guajira": "la guajira", "norte santander": "norte de santander"}
# Generic words dropped from a provider-name search if the full phrase matches nothing.
_GENERIC = {"hospital", "clinica", "ips", "centro", "de", "del", "la", "el", "los", "las", "salud", "medico",
            "medica", "sede", "e", "y"}
_MAX_PROVIDER_CODES = 60


@dataclass
class Resolution:
    status: Literal["ok", "ambiguous", "unknown"]
    value: str | None = None
    department: str | None = None
    candidates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProviderMatch:
    status: Literal["ok", "ambiguous", "unknown", "too_many"]
    codes: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)


class Lexicon:
    def __init__(self, data: dict[str, Any]) -> None:
        self.built_at: str | None = data.get("built_at")
        cutoff = data.get("source_cutoff")
        self.cutoff_raw: str | None = cutoff if isinstance(cutoff, str) else None
        self._departments: list[dict[str, Any]] = data.get("departments", [])
        self._dept_by_norm = {d["norm"]: d["value"] for d in self._departments}
        self._munis: list[dict[str, Any]] = data.get("municipalities", [])
        self._munis_by_norm: dict[str, list[dict[str, Any]]] = {}
        for m in self._munis:
            self._munis_by_norm.setdefault(m["norm"], []).append(m)
        self._providers: list[dict[str, Any]] = data.get("providers", [])
        self._capacity: list[dict[str, Any]] = data.get("capacity", [])
        self._groups = sorted({c["group"] for c in self._capacity})

    @classmethod
    def load(cls, path: Path) -> Lexicon:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @property
    def department_names(self) -> list[str]:
        return [d["value"] for d in self._departments]

    @property
    def capacity_groups(self) -> list[str]:
        return list(self._groups)

    def provider_entries(self, codes: list[str]) -> list[dict[str, Any]]:
        """Lexicon rows (name, municipality, department) of these provider codes -- names only, never figures."""
        wanted = set(codes)
        return [p for p in self._providers if p["code"] in wanted]

    def top_departments(self, n: int = 3) -> list[str]:
        return [d["value"] for d in sorted(self._departments, key=lambda d: -d.get("providers", 0))[:n]]

    # -- generic closed-list resolution -------------------------------------

    @staticmethod
    def _resolve_in(text: str, by_norm: dict[str, str]) -> Resolution:
        n = norm(text)
        n = _ALIASES.get(n, n)
        if n in by_norm:
            value = by_norm[n]
            return Resolution("ok", value, warnings=[] if value == text else ["FILTER_NORMALIZED"])
        prefixed = [v for k, v in by_norm.items() if k.startswith(n + " ") or k.startswith(n)]
        if len(prefixed) == 1 and len(n) >= 4:
            return Resolution("ok", prefixed[0], warnings=["FILTER_NORMALIZED"])
        close = difflib.get_close_matches(n, list(by_norm), n=3, cutoff=0.75)
        if len(close) == 1 and difflib.SequenceMatcher(None, n, close[0]).ratio() >= 0.9:
            return Resolution("ok", by_norm[close[0]], warnings=["FILTER_NORMALIZED"])
        if close or len(prefixed) > 1:
            cands = [by_norm[c] for c in close] or prefixed[:3]
            return Resolution("ambiguous", candidates=cands[:3])
        return Resolution("unknown")

    def resolve_department(self, text: str) -> Resolution:
        res = self._resolve_in(text, self._dept_by_norm)
        if res.status == "ok" and res.value in DISTRICTS.values():
            res.warnings.append("DISTRICT_AS_DEPARTMENT")
        if res.status == "ok" and res.value in DISTRICTS:
            res.warnings.append("DISTRICT_AS_DEPARTMENT")
        return res

    def resolve_municipality(self, text: str, department: str | None = None) -> Resolution:
        n = norm(text)
        entries = self._munis_by_norm.get(n)
        warnings: list[str] = []
        if not entries:
            close = difflib.get_close_matches(n, list(self._munis_by_norm), n=3, cutoff=0.8)
            if len(close) == 1 and difflib.SequenceMatcher(None, n, close[0]).ratio() >= 0.9:
                entries, warnings = self._munis_by_norm[close[0]], ["FILTER_NORMALIZED"]
            elif close:
                cands = [f"{e['value']} ({e['department']})" for c in close for e in self._munis_by_norm[c]]
                return Resolution("ambiguous", candidates=cands[:3])
            else:
                return Resolution("unknown")
        if department:
            inside = [e for e in entries if e["department"] == department]
            if inside:
                entries = inside
            else:
                # "Cali, Valle del Cauca": the source lists Cali as its own "department".
                districts = [e for e in entries if DISTRICTS.get(e["department"]) == department]
                if len(districts) == 1:
                    entries = districts
                    warnings.append("DISTRICT_AS_DEPARTMENT")
                else:
                    cands = [f"{e['value']} ({e['department']})" for e in entries]
                    return Resolution("ambiguous", candidates=cands[:3])
        if len(entries) > 1:
            return Resolution("ambiguous", candidates=[f"{e['value']} ({e['department']})" for e in entries][:3])
        e = entries[0]
        if e["value"] != text and "FILTER_NORMALIZED" not in warnings:
            warnings.append("FILTER_NORMALIZED")
        if e["department"] in DISTRICTS and "DISTRICT_AS_DEPARTMENT" not in warnings:
            warnings.append("DISTRICT_AS_DEPARTMENT")
        return Resolution("ok", e["value"], department=e["department"], warnings=warnings)

    def resolve_capacity_group(self, text: str) -> Resolution:
        by_norm = {norm(g): g for g in self._groups}
        n = norm(text)
        singular = {norm(g).rstrip("s"): g for g in self._groups}
        if n.rstrip("s") in singular:
            g = singular[n.rstrip("s")]
            return Resolution("ok", g, warnings=[] if g == text else ["FILTER_NORMALIZED"])
        return self._resolve_in(text, by_norm)

    def resolve_capacity_type(self, group: str, text: str) -> Resolution:
        by_norm = {norm(c["type"]): c["type"] for c in self._capacity if c["group"] == group and c.get("type")}
        res = self._resolve_in(text, by_norm)
        if res.status == "ok":
            return res
        # Bench 2026-10-09: Gemini sent "camas de adultos" for CAMAS/Adultos. Drop the group
        # word ("camas", "cama") and connectors before giving up.
        g = norm(group)
        words = [w for w in norm(text).split() if w not in {g, g.rstrip("s"), "de", "del", "para", "en"}]
        stripped = " ".join(words)
        if stripped and stripped != norm(text):
            retry = self._resolve_in(stripped, by_norm)
            if retry.status == "ok":
                retry.warnings = list(dict.fromkeys(retry.warnings + ["FILTER_NORMALIZED"]))
                return retry
        return res

    # -- provider names ------------------------------------------------------

    def find_providers(
        self, text: str, *, department: str | None = None, municipality: str | None = None
    ) -> ProviderMatch:
        """Map a spoken provider name to provider codes, within the location filters."""
        pool = [
            p
            for p in self._providers
            if (department is None or p["department"] == department)
            and (municipality is None or p["municipality"] == municipality)
        ]
        tokens = norm(text).split()
        hits = self._match(pool, tokens)
        if not hits:
            hits = self._match(pool, [t for t in tokens if t not in _GENERIC])
        if not hits:
            names = sorted({p["norm"] for p in pool})
            close = difflib.get_close_matches(norm(text), names, n=3, cutoff=0.6)
            hits = [p for p in pool if p["norm"] in close]
            if not hits:
                return ProviderMatch("unknown")
            status: Literal["ok", "ambiguous"] = "ambiguous"
        else:
            status = "ok"
        codes = sorted({p["code"] for p in hits})
        departments = sorted({p["department"] for p in hits})
        cands = []
        for p in hits:
            label = f"{p['name']} ({p['municipality']}, {p['department']})"
            if label not in cands:
                cands.append(label)
        if status == "ambiguous":
            return ProviderMatch("ambiguous", codes, cands[:3], departments)
        if len(codes) > _MAX_PROVIDER_CODES:
            return ProviderMatch("too_many", codes, cands[:3], departments)
        return ProviderMatch("ok", codes, cands[:3], departments)

    @staticmethod
    def _match(pool: list[dict[str, Any]], tokens: list[str]) -> list[dict[str, Any]]:
        if not tokens:
            return []
        return [p for p in pool if all(t in p["norm"].split() or t in p["norm"] for t in tokens)]
