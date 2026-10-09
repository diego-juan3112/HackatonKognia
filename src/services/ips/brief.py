"""Live dataset brief (docs/09 section 8): ``GET /dataset/brief``.

Three live queries, every figure from the source (R-22). The first one runs
alone to warm the connection; the other two then run in parallel (G3: three
at once opened three cold connections and took longer).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from models.ips import Deadline
from models.ports import DatasetPort
from services.ips import soql

TITLE = "Relación de IPS públicas y privadas según el nivel de atención y capacidad instalada"
LIMITS = ["Capacidad instalada, no disponibilidad", "Sin geolocalización", "Nivel vacío en la mayoría de las IPS"]


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", ".")


class BriefService:
    def __init__(self, dataset: DatasetPort, *, source_url: str, cutoff_raw: str | None, deadline_s: float = 6.0):
        self._dataset = dataset
        self._source_url = source_url
        self._cutoff_raw = cutoff_raw or ""

    async def build(self, bypass_cache: bool = False) -> dict[str, Any]:
        deadline = Deadline(6.0)
        t0 = time.perf_counter()
        counts = await self._dataset.query(soql.brief_counts(), deadline=deadline, bypass_cache=bypass_cache)
        nature_sql = ("SELECT naturaleza, count(DISTINCT c_digo_prestador) AS value "
                      "GROUP BY naturaleza ORDER BY value DESC")
        dept_sql = ("SELECT departamento, count(DISTINCT c_digo_prestador) AS value "
                    "GROUP BY departamento ORDER BY value DESC LIMIT 5")
        nature, depts = await asyncio.gather(
            self._dataset.query(nature_sql, deadline=deadline, bypass_cache=bypass_cache),
            self._dataset.query(dept_sql, deadline=deadline, bypass_cache=bypass_cache),
        )
        row = counts.rows[0] if counts.rows else {}
        stats = {
            "rows": int(row.get("rows", 0)),
            "providers": int(row.get("providers", 0)),
            "site_codes": int(row.get("site_codes", 0)),
            "fetched_at": counts.fetched_at,
            "ms": int((time.perf_counter() - t0) * 1000),
            "cache_status": counts.cache_status,
        }
        by_nature = [{"key": r.get("naturaleza"), "value": int(r.get("value", 0))} for r in nature.rows]
        top_departments = [{"key": r.get("departamento"), "value": int(r.get("value", 0))} for r in depts.rows]
        top = top_departments[0]["key"] if top_departments else "Antioquia"
        questions = [
            "¿Cuántas IPS públicas, privadas y mixtas hay?",
            f"¿Cuántas IPS públicas hay en {top}?",
            "¿Cuántas camas de adultos hay en total?",
            "¿Qué municipios tienen más camas?",
            f"Busca hospitales San José en {top_departments[1]['key'] if len(top_departments) > 1 else top}",
        ]
        spoken = (
            "Soy un asistente de inteligencia artificial. Consulto en vivo el registro de IPS del Ministerio de "
            f"Salud, con corte a noviembre de 2022: {_fmt(stats['providers'])} prestadores y "
            f"{_fmt(stats['site_codes'])} códigos de sede. Pregúntame, por ejemplo: cuántas IPS públicas, "
            "privadas y mixtas hay, o qué municipios tienen más camas."
        )
        return {
            "title": TITLE,
            "source": {"name": "MinSalud — REPS", "license": "CC BY-SA 4.0", "cutoff_raw": self._cutoff_raw,
                       "cutoff_date": "2022-11-05", "url": self._source_url},
            "stats": stats,
            "by_nature": by_nature,
            "top_departments": top_departments,
            "limits": LIMITS,
            "suggested_questions": questions,
            "spoken_brief": spoken,
            "trace": [{"soql": r.soql, "ms": r.ms, "rows": len(r.rows), "cache_status": r.cache_status}
                      for r in (counts, nature, depts)],
        }
