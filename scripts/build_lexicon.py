"""Build data/lexicon.json from the live dataset (docs/09 section 7).

    python -m scripts.build_lexicon

Grouped, paged SODA3 queries for departments, municipalities, provider names
and capacity groups/types. The lexicon only normalises names and proposes
candidates; it is **never** a source of figures (R-22). Rebuild before the demo.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config import get_settings  # noqa: E402
from integrations.datasets.socrata_client import SocrataClient  # noqa: E402
from models.ips import Deadline  # noqa: E402
from services.ips.normalize import norm  # noqa: E402

PAGE = 5000
QUERIES = {
    "departments": "SELECT departamento, count(DISTINCT c_digo_prestador) AS providers GROUP BY departamento ORDER BY departamento",
    "municipalities": "SELECT departamento, municipio GROUP BY departamento, municipio ORDER BY departamento, municipio",
    "providers": (
        "SELECT c_digo_prestador, nombre_prestador, municipio, departamento "
        "GROUP BY c_digo_prestador, nombre_prestador, municipio, departamento "
        "ORDER BY c_digo_prestador, municipio"
    ),
    "capacity": (
        "SELECT nom_grupo_capacidad, nom_descripcion_capacidad "
        "GROUP BY nom_grupo_capacidad, nom_descripcion_capacidad "
        "ORDER BY nom_grupo_capacidad, nom_descripcion_capacidad"
    ),
    "cutoff": "SELECT fecha_corte GROUP BY fecha_corte",
}


async def _paged(client: SocrataClient, soql: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        page = await client.query(f"{soql} LIMIT {PAGE} OFFSET {offset}", deadline=Deadline(60), bypass_cache=True)
        rows.extend(page.rows)
        if len(page.rows) < PAGE:
            return rows
        offset += PAGE


async def build() -> dict:
    s = get_settings()
    client = SocrataClient(
        base_url=s.dataset_base_url,
        dataset_id=s.dataset_id,
        app_token=s.datos_gov_app_token,
        connect_timeout_s=10,
        read_timeout_s=30,
        page_size=PAGE,
    )
    try:
        res = {name: await _paged(client, soql) for name, soql in QUERIES.items()}
    finally:
        await client.aclose()
    cutoffs = [r.get("fecha_corte") for r in res["cutoff"] if r.get("fecha_corte")]
    return {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset_id": s.dataset_id,
        "source_cutoff": cutoffs[0] if len(cutoffs) == 1 else cutoffs,
        "departments": [
            {"value": r["departamento"], "norm": norm(r["departamento"]), "providers": int(r["providers"])}
            for r in res["departments"]
        ],
        "municipalities": [
            {"value": r["municipio"], "norm": norm(r["municipio"]), "department": r["departamento"]}
            for r in res["municipalities"]
        ],
        "providers": [
            {
                "code": r["c_digo_prestador"],
                "name": r["nombre_prestador"],
                "norm": norm(r["nombre_prestador"]),
                "municipality": r["municipio"],
                "department": r["departamento"],
            }
            for r in res["providers"]
        ],
        "capacity": [
            {"group": r["nom_grupo_capacidad"], "type": r.get("nom_descripcion_capacidad")} for r in res["capacity"]
        ],
    }


def main() -> None:
    t0 = time.perf_counter()
    lexicon = asyncio.run(build())
    out = get_settings().lexicon_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lexicon, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        f"{out}: {out.stat().st_size / 1024:.0f} KB in {time.perf_counter() - t0:.1f} s -- "
        f"{len(lexicon['departments'])} departments, {len(lexicon['municipalities'])} municipalities, "
        f"{len(lexicon['providers'])} provider rows, {len(lexicon['capacity'])} capacity types; "
        f"cutoff {lexicon['source_cutoff']!r}"
    )


if __name__ == "__main__":
    main()
