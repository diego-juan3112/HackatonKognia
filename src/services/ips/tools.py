"""The five IPS tools (docs/09 section 4) and the evidence envelope (section 5).

Determinism lives here (D-14): the voice engine chooses *which* tool to call;
this service validates the arguments against closed lists and the lexicon,
builds the query, and is the only place that decides grain, unit, status and
warnings. ``unavailable`` is never turned into ``empty``; nothing is invented.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from models.ips import (
    TOOL_ARGS,
    AggregateIpsArgs,
    CompareIpsArgs,
    CorrectContextArgs,
    DatasetUnavailable,
    Deadline,
    Evidence,
    GetIpsDetailsArgs,
    QueryResult,
    SearchIpsArgs,
    ToolEnvelope,
    ToolError,
    ToolRequest,
    Trace,
)
from models.ports import DatasetPort
from services.ips import for_model, soql
from services.ips.lexicon import Lexicon

ALWAYS_WARN = ["CUTOFF_2022"]
# evidence.unit is a code; data.unit is the Spanish label the UI shows.
UNIT_LABELS = {"providers": "prestadores", "site_codes": "códigos de sede", "sites": "sedes"}
_CACHE_RANK = {"live": 0, "fresh": 1, "stale": 2}
_MAX_IDEMPOTENT = 2000


class _Reject(Exception):
    """Short-circuit a tool with a non-ok envelope (ambiguous / invalid / empty)."""

    def __init__(self, status: str, *, data: dict[str, Any] | None = None, error: ToolError | None = None,
                 warnings: list[str] | None = None) -> None:
        super().__init__(status)
        self.status = status
        self.data = data or {}
        self.error = error
        self.warnings = warnings or []


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _label(unit: str) -> str:
    return UNIT_LABELS.get(unit, unit)


def _num(value: Any) -> int | float | None:
    """Socrata sends every number as text; null stays None (null != 0)."""
    if value is None or value == "":
        return None
    f = float(value)
    return int(f) if f.is_integer() else f


class IpsToolService:
    def __init__(
        self,
        dataset: DatasetPort,
        lexicon: Lexicon,
        *,
        dataset_id: str,
        source_url: str,
        cursor_key: bytes,
        deadline_s: float = 6.0,
    ) -> None:
        self._dataset = dataset
        self._lex = lexicon
        self._dataset_id = dataset_id
        self._source_url = source_url
        self._cursor_key = cursor_key
        self._deadline_s = deadline_s
        self._done: OrderedDict[tuple[str, str, int], ToolEnvelope] = OrderedDict()
        self._handlers: dict[str, Callable[..., Awaitable[ToolEnvelope]]] = {
            "search_ips": self._search_ips,
            "get_ips_details": self._get_ips_details,
            "aggregate_ips": self._aggregate_ips,
            "compare_ips": self._compare_ips,
            "correct_context": self._correct_context,
        }

    # Most likely questions (brief suggestions and the demo script). Prefetching them
    # through the tools themselves guarantees the SoQL is byte-identical to what the
    # model will ask, so the 60 s cache hits and the answer is labelled "fresh".
    LIKELY: tuple[tuple[str, dict[str, Any]], ...] = (
        ("aggregate_ips", {"metric": "provider_count"}),
        ("aggregate_ips", {"metric": "provider_count", "group_by": "nature"}),
        ("aggregate_ips", {"metric": "site_count", "group_by": "nature"}),
        ("aggregate_ips", {"metric": "capacity_sum", "filters": {"capacity_group": "CAMAS"}}),
        ("aggregate_ips", {"metric": "provider_count", "group_by": "department", "top_n": 5}),
        ("aggregate_ips", {"metric": "capacity_sum", "group_by": "municipality", "top_n": 5,
                           "filters": {"capacity_group": "CAMAS"}}),
        # Added after the bench (fresh answers took 2.3-3.7 s vs live +0.5-1.6 s).
        ("aggregate_ips", {"metric": "provider_count", "group_by": "level"}),
        ("aggregate_ips", {"metric": "site_count"}),
        ("aggregate_ips", {"metric": "capacity_sum", "filters": {"capacity_group": "CAMAS", "capacity_type": "Adultos"}}),
        ("aggregate_ips", {"metric": "capacity_sum", "filters": {"capacity_group": "AMBULANCIAS"}}),
    )

    async def prefetch(self) -> int:
        """Warm the dataset cache with the likely aggregates, in parallel. Never raises."""
        async def one(name: str, args: dict[str, Any]) -> bool:
            try:
                parsed = TOOL_ARGS[name].model_validate(args)
                req = ToolRequest(tool_call_id=f"prefetch:{name}", args=args)
                env = await self._handlers[name](req, parsed, Deadline(self._deadline_s))
                return env.status == "ok"
            except Exception:  # noqa: BLE001 -- best effort, off the critical path
                return False
        results = await asyncio.gather(*(one(n, a) for n, a in self.LIKELY))
        return sum(results)

    # -- entry point ---------------------------------------------------------

    async def run(self, name: str, req: ToolRequest, scope: str = "") -> ToolEnvelope:
        # ``scope`` = the caller's session id: several evaluators at once must never share an
        # idempotent result, even if their engines happen to produce the same tool_call_id.
        key = (scope, req.tool_call_id, req.context.state_version)
        if key in self._done:  # docs/08 section 5.5: same call + same state -> same result
            return self._done[key]
        if name not in self._handlers:
            raise KeyError(name)
        try:
            args = TOOL_ARGS[name].model_validate(req.args)
        except ValidationError as exc:
            return self._envelope(req, "invalid", error=ToolError(
                code="INVALID_ARGS", message="Argumentos inválidos para la herramienta.",
                hint=_validation_hint(exc), retryable=True))
        deadline = Deadline(self._deadline_s)
        try:
            env = await self._handlers[name](req, args, deadline)
        except _Reject as r:
            env = self._envelope(req, r.status, data=r.data, error=r.error, warnings=r.warnings)
        except DatasetUnavailable as exc:
            env = self._envelope(req, "unavailable", error=ToolError(
                code=exc.code, message="La fuente datos.gov.co no respondió a tiempo.", retryable=True))
        env.for_model = for_model.render(name, env)
        if env.status in ("ok", "empty"):
            self._done[key] = env
            while len(self._done) > _MAX_IDEMPOTENT:
                self._done.popitem(last=False)
        return env

    # -- helpers -------------------------------------------------------------

    def _envelope(self, req: ToolRequest, status: str, *, data: dict[str, Any] | None = None,
                  results: list[QueryResult] | None = None, unit: str | None = None,
                  filters: dict[str, Any] | None = None, warnings: list[str] | None = None,
                  complete: bool = True, error: ToolError | None = None, next_cursor: str | None = None,
                  context_patch: dict[str, Any] | None = None, state_version: int | None = None) -> ToolEnvelope:
        results = results or []
        warns = list(dict.fromkeys(ALWAYS_WARN + (warnings or [])))
        traces = [Trace(engine=r.engine, soql=r.soql, ms=r.ms, rows=len(r.rows), cache_status=r.cache_status)
                  for r in results]
        if results:
            cache = max((r.cache_status for r in results), key=lambda c: _CACHE_RANK[c])
            if cache == "stale":
                warns.append("STALE_CACHE")
            fingerprint = hashlib.sha256("\n".join(r.soql for r in results).encode()).hexdigest()
            fetched_at = max(r.fetched_at for r in results)
            trace = Trace(engine=results[0].engine, soql="\n".join(r.soql for r in results),
                          ms=max(r.ms for r in results), rows=sum(len(r.rows) for r in results), cache_status=cache)
        else:
            # No query ran (invalid, ambiguous, a correction): still a keyed, honest envelope.
            cache = "live"
            fingerprint = hashlib.sha256(f"{req.tool_call_id}:{status}".encode()).hexdigest()
            fetched_at = _now_iso()
            trace = Trace(soql="", ms=0, rows=0, cache_status="live")
            complete = complete and status == "ok"
        evidence = Evidence(
            dataset_id=self._dataset_id, source_url=self._source_url,
            query_fingerprint=f"sha256:{fingerprint}", cutoff_raw=self._lex.cutoff_raw,
            fetched_at=fetched_at, cache_status=cache, complete=complete,  # type: ignore[arg-type]
            unit=unit, filters=filters or {}, warnings=warns,
        )
        return ToolEnvelope(
            tool_call_id=req.tool_call_id, turn_id=req.turn_id or req.context.turn_id,
            state_version=req.context.state_version if state_version is None else state_version,
            status=status, data=data or {}, evidence=evidence, trace=trace, traces=traces,  # type: ignore[arg-type]
            error=error, next_cursor=next_cursor, context_patch=context_patch or {},
        )

    async def _q(self, sql: str, deadline: Deadline, bypass: bool) -> QueryResult:
        soql.assert_safe(sql)
        return await self._dataset.query(sql, deadline=deadline, bypass_cache=bypass)

    def _resolve_location(self, department: str | None, municipality: str | None
                          ) -> tuple[dict[str, str | None], list[str]]:
        """Resolve department/municipality or raise an ambiguous/invalid envelope."""
        resolved: dict[str, str | None] = {"department": None, "municipality": None}
        warnings: list[str] = []
        if department:
            d = self._lex.resolve_department(department)
            if d.status == "ambiguous":
                raise _Reject("ambiguous", data={"field": "department", "candidates": d.candidates,
                                                 "question": "¿A cuál departamento te refieres?"})
            if d.status == "unknown":
                raise _Reject("invalid", error=ToolError(
                    code="UNKNOWN_ENTITY", message=f"No reconozco el departamento «{department}».",
                    hint="Usa un departamento de Colombia; ej.: " + ", ".join(self._lex.top_departments()),
                    retryable=True))
            resolved["department"], warnings = d.value, warnings + d.warnings
        if municipality:
            m = self._lex.resolve_municipality(municipality, resolved["department"])
            if m.status == "ambiguous":
                raise _Reject("ambiguous", data={"field": "municipality", "candidates": m.candidates,
                                                 "question": "¿De qué departamento es ese municipio?"})
            if m.status == "unknown":
                raise _Reject("invalid", error=ToolError(
                    code="UNKNOWN_ENTITY", message=f"No encuentro el municipio «{municipality}».",
                    hint="Confirma el nombre del municipio y su departamento.", retryable=True))
            resolved["municipality"], warnings = m.value, warnings + m.warnings
            resolved["department"] = m.department  # a district resolves to its own "department"
        return resolved, list(dict.fromkeys(warnings))

    def _resolve_capacity(self, group: str | None, ctype: str | None) -> tuple[str | None, str | None, list[str]]:
        if not group:
            if ctype:
                raise _Reject("invalid", error=ToolError(
                    code="INVALID_ARGS", message="Falta el grupo de capacidad.",
                    hint="Indica capacity_group (p. ej. CAMAS) junto con capacity_type.", retryable=True))
            return None, None, []
        g = self._lex.resolve_capacity_group(group)
        if g.status != "ok":
            raise _Reject("ambiguous" if g.candidates else "invalid", data={"field": "capacity_group",
                          "candidates": g.candidates}, error=None if g.candidates else ToolError(
                          code="UNKNOWN_ENTITY", message=f"Grupo de capacidad desconocido: «{group}».",
                          hint="Grupos: AMBULANCIAS, CAMAS, CAMILLAS, CONSULTORIOS, SALAS, SILLAS, UNIDAD MOVIL",
                          retryable=True))
        warnings = list(g.warnings)
        if not ctype:
            return g.value, None, warnings
        t = self._lex.resolve_capacity_type(g.value or "", ctype)
        if t.status != "ok":
            raise _Reject("ambiguous" if t.candidates else "invalid", data={"field": "capacity_type",
                          "candidates": t.candidates}, error=None if t.candidates else ToolError(
                          code="UNKNOWN_ENTITY", message=f"Tipo de capacidad desconocido: «{ctype}».",
                          hint=f"Revisa los tipos del grupo {g.value}.", retryable=True))
        return g.value, t.value, warnings + t.warnings

    def _resolve_name(self, name: str | None, loc: dict[str, str | None]) -> tuple[list[str] | None, list[str]]:
        if not name:
            return None, []
        match = self._lex.find_providers(name, department=loc["department"], municipality=loc["municipality"])
        if match.status == "unknown":
            raise _Reject("empty", data={"reason": f"Ningún prestador coincide con «{name}» en ese filtro."})
        located = loc["department"] or loc["municipality"]
        if match.status == "ambiguous" or (len(match.departments) > 1 and not located):
            # A-04: never pick the first match; ask for the location.
            raise _Reject("ambiguous", data={
                "field": "department" if len(match.departments) > 1 and not located else "name",
                "candidates": match.departments[:3] if len(match.departments) > 1 and not located
                else match.candidates,
                "question": "¿En qué departamento o municipio?" if len(match.departments) > 1 and not located
                else "¿Cuál de estos prestadores?"})
        if match.status == "too_many":
            raise _Reject("ambiguous", data={"field": "municipality", "candidates": match.departments[:3],
                                             "question": "Hay muchas coincidencias: ¿en qué municipio?"})
        return match.codes, []

    # -- cursors (opaque signed offsets) --------------------------------------

    def _cursor(self, offset: int, fingerprint: str) -> str:
        raw = json.dumps({"o": offset, "f": fingerprint[:16]}, separators=(",", ":")).encode()
        sig = hmac.new(self._cursor_key, raw, hashlib.sha256).digest()[:12]
        return base64.urlsafe_b64encode(raw + sig).decode().rstrip("=")

    def _offset(self, cursor: str | None, fingerprint: str) -> int:
        if not cursor:
            return 0
        try:
            blob = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
            raw, sig = blob[:-12], blob[-12:]
            ok = hmac.compare_digest(sig, hmac.new(self._cursor_key, raw, hashlib.sha256).digest()[:12])
            data = json.loads(raw)
            if ok and data["f"] == fingerprint[:16]:
                return int(data["o"])
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
        raise _Reject("invalid", error=ToolError(code="INVALID_CURSOR", message="Cursor inválido o de otra búsqueda.",
                                                 hint="Repite la búsqueda sin cursor.", retryable=True))

    # -- tools ---------------------------------------------------------------

    async def _search_ips(self, req: ToolRequest, a: SearchIpsArgs, deadline: Deadline) -> ToolEnvelope:
        if not any([a.department, a.municipality, a.name, a.nature, a.level]):
            raise _Reject("invalid", error=ToolError(
                code="INVALID_ARGS", message="La búsqueda necesita al menos un filtro.",
                hint="Agrega department, municipality, name, nature o level.", retryable=True))
        loc, warnings = self._resolve_location(a.department, a.municipality)
        codes, _ = self._resolve_name(a.name, loc)
        filters = {**loc, "nature": a.nature, "level": str(a.level) if a.level else None}
        where_sql = soql.where(filters, codes)
        fingerprint = hashlib.sha256(where_sql.encode()).hexdigest()
        offset = self._offset(a.cursor, fingerprint)
        res = await self._q(soql.search_sites(where_sql, a.limit + 1, offset), deadline, req.bypass_cache)
        rows = res.rows[: a.limit]
        more = len(res.rows) > a.limit
        items = [_site(r) for r in rows]
        if a.level:
            warnings.append("LEVEL_MISSING_MOSTLY")
        if more:
            warnings.append("PARTIAL_RESULT")
        status = "ok" if items else "empty"
        shown = {k: v for k, v in {**filters, "name": a.name}.items() if v}
        return self._envelope(
            req, status, data={"items": items, "count_returned": len(items)}, results=[res], unit="sites",
            filters=shown, warnings=warnings + ["SITE_CODES_NOT_PHYSICAL_SITES"], complete=not more,
            next_cursor=self._cursor(offset + a.limit, fingerprint) if more else None,
            context_patch={"confirmed_filters": {k: v for k, v in loc.items() if v},
                           "last_result_site_keys": [i["site_key"] for i in items]},
        )

    async def _get_ips_details(self, req: ToolRequest, a: GetIpsDetailsArgs, deadline: Deadline) -> ToolEnvelope:
        provider, site_code, site_number = a.site_key.split(":")
        key_sql = soql.site_key_clause(provider, site_code, site_number)
        group, ctype, warnings = self._resolve_capacity(a.capacity_group, a.capacity_type)
        cap_sql = key_sql + ("" if not group else " AND " + soql.where(
            {"capacity_group": group, "capacity_type": ctype}))
        bypass = req.bypass_cache
        info, caps = await asyncio.gather(
            self._q(soql.site_info(key_sql, a.include_contact), deadline, bypass),
            self._q(soql.site_capacities(cap_sql), deadline, bypass),
        )
        if not info.rows:
            return self._envelope(req, "empty", data={"reason": "No existe una sede con ese site_key."},
                                  results=[info], unit="site", filters={"site_key": a.site_key})
        site = _site(info.rows[0])
        if a.include_contact:
            site["contact"] = {k: info.rows[0].get(soql.col(k)) for k in soql.CONTACT_COLUMNS}
            warnings.append("CONTACT_HISTORICAL")
        capacities = [{"group": r.get(soql.col("capacity_group")), "type": r.get(soql.col("capacity_type")),
                       "quantity": _num(r.get("quantity"))} for r in caps.rows]
        if any(c["quantity"] is None for c in capacities):
            warnings.append("NULL_NOT_ZERO")
        if site["level"] is None:
            warnings.append("LEVEL_MISSING_MOSTLY")
        return self._envelope(
            req, "ok", data={"site": site, "capacities": capacities}, results=[info, caps], unit="installed_capacity",
            filters={"site_key": a.site_key, "capacity_group": group, "capacity_type": ctype},
            warnings=warnings + ["NOT_AVAILABILITY"],
            context_patch={"selected_site_keys": [a.site_key]},
        )

    async def _aggregate_ips(self, req: ToolRequest, a: AggregateIpsArgs, deadline: Deadline) -> ToolEnvelope:
        f = a.filters
        loc, warnings = self._resolve_location(f.department, f.municipality)
        codes, _ = self._resolve_name(f.name, loc)
        group, ctype, cap_warn = self._resolve_capacity(f.capacity_group, f.capacity_type)
        warnings += cap_warn
        if a.metric == "capacity_sum" and not group:
            raise _Reject("invalid", error=ToolError(
                code="INVALID_ARGS", message="Para sumar capacidad hace falta el grupo.",
                hint="Indica filters.capacity_group (CAMAS, SALAS, CAMILLAS...). Nunca se suman grupos distintos.",
                retryable=True))
        if a.metric == "capacity_sum" and not ctype:
            warnings.append("MIXED_TYPES")
        if a.metric == "site_count":
            warnings.append("SITE_CODES_NOT_PHYSICAL_SITES")
        if a.metric == "capacity_sum":
            warnings.append("NOT_AVAILABILITY")
        if f.level or a.group_by == "level":
            warnings.append("LEVEL_MISSING_MOSTLY")
        filters = {**loc, "nature": f.nature, "level": str(f.level) if f.level else None,
                   "capacity_group": group, "capacity_type": ctype}
        where_sql = soql.where(filters, codes)
        unit = {"provider_count": "providers", "site_count": "site_codes"}.get(a.metric) or (group or "").lower()
        limit = a.top_n or (None if a.group_by in ("nature", "level") else 10)
        res = await self._q(soql.aggregate(a.metric, where_sql, a.group_by, a.order, limit), deadline,
                            req.bypass_cache)
        shown = {k: v for k, v in {**filters, "name": f.name}.items() if v}
        patch = {"confirmed_filters": {k: v for k, v in loc.items() if v}}
        if not a.group_by:
            value = _num(res.rows[0].get("value")) if res.rows else None
            status = "ok" if value else "empty"
            return self._envelope(req, status, data={"value": value, "unit": _label(unit), "metric": a.metric,
                                                     "complete": True},
                                  results=[res], unit=unit, filters=shown, warnings=warnings, context_patch=patch)
        cols = [soql.col(c) for c in soql.GROUP_COLUMNS[a.group_by]]
        groups = []
        for r in res.rows:
            key = r.get(cols[0])  # the null level group arrives without the key (docs/09 section 4)
            item: dict[str, Any] = {"key": key, "value": _num(r.get("value"))}
            if a.group_by == "level":
                item["label"] = f"nivel {key}" if key else "sin nivel registrado"
            if a.group_by == "municipality":
                # Same key the web mocks use; the parts stay separate for the model.
                item.update(key=f"{key} · {r.get(cols[1])}", municipality=key, department=r.get(cols[1]))
            groups.append(item)
        # An explicit top_n *is* the requested set; the default cap of 10 is not.
        complete = a.top_n is not None or limit is None or len(groups) < limit
        if not complete:
            warnings.append("PARTIAL_RESULT")
        return self._envelope(req, "ok" if groups else "empty",
                              data={"groups": groups, "unit": _label(unit), "metric": a.metric, "group_by": a.group_by,
                                    "complete": complete},
                              results=[res], unit=unit, filters=shown, warnings=warnings, complete=complete,
                              context_patch=patch)

    async def _compare_ips(self, req: ToolRequest, a: CompareIpsArgs, deadline: Deadline) -> ToolEnvelope:
        keys = []
        for k in a.site_keys:
            parts = k.split(":")
            if len(parts) != 3 or not all(parts):
                raise _Reject("invalid", error=ToolError(code="INVALID_ARGS", message=f"site_key inválido: {k}",
                                                         hint="Formato provider_code:site_code:site_number",
                                                         retryable=True))
            keys.append(parts)
        group, ctype, warnings = self._resolve_capacity(a.capacity_group, a.capacity_type)
        if not ctype:
            warnings.append("MIXED_TYPES")
        res = await self._q(soql.compare_sites([soql.site_key_clause(*k) for k in keys],
                                               soql.where({"capacity_group": group, "capacity_type": ctype})),
                            deadline, req.bypass_cache)
        by_key = {":".join([r.get(soql.col("provider_code"), ""), r.get(soql.col("site_code"), ""),
                            r.get(soql.col("site_number"), "")]): r for r in res.rows}
        items = []
        for k in a.site_keys:
            row = by_key.get(k)
            items.append({"site_key": k, "site_name": row.get(soql.col("site_name")) if row else None,
                          "quantity": _num(row.get("quantity")) if row else None,
                          "known": bool(row and row.get("quantity") is not None)})
        if any(not i["known"] for i in items):
            warnings.append("NULL_NOT_ZERO")
        return self._envelope(req, "ok", data={"items": items, "capacity_group": group, "capacity_type": ctype},
                              results=[res], unit=(group or "").lower(),
                              filters={"site_keys": a.site_keys, "capacity_group": group, "capacity_type": ctype},
                              warnings=warnings + ["NOT_AVAILABILITY"])

    async def _correct_context(self, req: ToolRequest, a: CorrectContextArgs, deadline: Deadline) -> ToolEnvelope:
        current = req.context.state_version
        expected = current if a.expected_state_version is None else a.expected_state_version
        target_turn = a.target_turn_id or req.context.turn_id or req.turn_id
        if expected != current:
            raise _Reject("invalid", error=ToolError(
                code="STATE_CONFLICT", message="El estado cambió; refresca el contexto.",
                hint=f"state_version vigente: {current}", retryable=True))
        confirmed: dict[str, Any] = {}
        warnings: list[str] = []
        if a.field in ("department", "municipality"):
            dept = req.context.confirmed_filters.get("department") if a.field == "municipality" else None
            loc, warnings = self._resolve_location(a.value if a.field == "department" else None,
                                                   a.value if a.field == "municipality" else None)
            if a.field == "municipality" and dept and loc["department"] != dept:
                # The corrected town lives elsewhere: the location changes as a whole.
                warnings.append("LOCATION_CHANGED")
            confirmed = {"department": loc["department"], "municipality": loc["municipality"]}
        elif a.field == "nature":
            value = {"publica": "Pública", "privada": "Privada", "mixta": "Mixta"}.get(
                a.value.strip().lower().replace("ú", "u"))
            if not value:
                raise _Reject("invalid", error=ToolError(code="INVALID_ARGS", message="Naturaleza inválida.",
                                                         hint="Pública, Privada o Mixta.", retryable=True))
            confirmed = {"nature": value}
        elif a.field == "level":
            if a.value.strip() not in ("1", "2", "3"):
                raise _Reject("invalid", error=ToolError(code="INVALID_ARGS", message="Nivel inválido.",
                                                         hint="1, 2 o 3.", retryable=True))
            confirmed = {"level": int(a.value.strip())}
        elif a.field == "site_key":
            if len(a.value.split(":")) != 3:
                raise _Reject("invalid", error=ToolError(code="INVALID_ARGS", message="site_key inválido.",
                                                         hint="provider_code:site_code:site_number", retryable=True))
            confirmed = {"site_key": a.value}
        else:
            confirmed = {"name": a.value}
        new_version = current + 1
        # Keys are CanonicalState fields (web/src/voice/types.ts): evidence and selections go.
        patch = {
            "state_version": new_version,
            "confirmed_filters": confirmed,
            "last_evidence_refs": [],
            "selected_site_keys": [] if a.field != "site_key" else [a.value],
            "last_result_site_keys": [],
            "invalidate_evidence": True,
            "corrects_turn_id": target_turn,
        }
        resolved = ", ".join(str(v) for v in confirmed.values() if v)
        return self._envelope(req, "ok", data={"field": a.field, "value": a.value, "resolved": resolved,
                                               "confirmed": confirmed},
                              unit="correction", filters=confirmed, warnings=warnings, context_patch=patch,
                              state_version=new_version)


def _site(r: dict[str, Any]) -> dict[str, Any]:
    c = soql.col
    level = r.get(c("level"))
    return {
        "site_key": f"{r.get(c('provider_code'))}:{r.get(c('site_code'))}:{r.get(c('site_number'))}",
        "provider_name": r.get(c("provider_name")),
        "site_name": r.get(c("site_name")),
        "municipality": r.get(c("municipality")),
        "department": r.get(c("department")),
        "nature": r.get(c("nature")),
        "level": int(level) if level else None,
    }


def _validation_hint(exc: ValidationError) -> str:
    parts = []
    for e in exc.errors()[:3]:
        loc = ".".join(str(x) for x in e.get("loc", ()))
        parts.append(f"{loc}: {e.get('msg')}")
    return "; ".join(parts)
