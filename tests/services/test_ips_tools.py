"""The five IPS tools against FakeDataset (R-16, R-17). Maps to A-03..A-09, A-12, A-17, A-26."""

from __future__ import annotations

import pytest

from models.ips import ToolRequest
from services.ips import soql
from services.ips.lexicon import Lexicon
from services.ips.tools import IpsToolService
from tests.doubles.fake_dataset import FakeDataset, unavailable
from tests.fixtures.lexicon_small import LEXICON


def _svc(ds: FakeDataset) -> IpsToolService:
    return IpsToolService(ds, Lexicon(LEXICON), dataset_id="s2ru-bqt6",
                          source_url="https://www.datos.gov.co/resource/s2ru-bqt6.json", cursor_key=b"k" * 32)


def _req(args: dict, call_id: str = "c1", state_version: int = 0, **extra) -> ToolRequest:
    return ToolRequest(tool_call_id=call_id, args=args,
                       context={"conversation_id": "conv", "turn_id": "t1", "state_version": state_version}, **extra)


async def test_provider_count_counts_distinct_providers_not_rows():  # A-05
    ds = FakeDataset().on("count(DISTINCT c_digo_prestador)", [{"value": "9320"}])
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "provider_count"}))
    assert ds.queries == ["SELECT count(DISTINCT c_digo_prestador) AS value"]
    assert env.status == "ok" and env.data["value"] == 9320 and env.data["unit"] == "prestadores"
    assert env.evidence.unit == "providers" and "CUTOFF_2022" in env.evidence.warnings
    assert env.evidence.cutoff_raw.startswith("Fecha corte REPS") and env.trace.rows == 1


async def test_group_by_level_null_group_has_no_key():
    rows = [{"value": "8325"}, {"num_nivel_atencion": "1", "value": "853"}]
    ds = FakeDataset().on("GROUP BY num_nivel_atencion", rows)
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "provider_count", "group_by": "level"}))
    assert env.data["groups"][0] == {"key": None, "value": 8325, "label": "sin nivel registrado"}
    assert "LEVEL_MISSING_MOSTLY" in env.evidence.warnings and env.data["complete"] is True


async def test_capacity_sum_requires_group_and_warns_mixed_types():
    ds = FakeDataset().on("sum(num_cantidad_capacidad_instalada)", [{"value": "97036"}])
    bad = await _svc(ds).run("aggregate_ips", _req({"metric": "capacity_sum"}))
    assert bad.status == "invalid" and bad.error and "capacity_group" in (bad.error.hint or "")
    ok = await _svc(ds).run("aggregate_ips", _req({"metric": "capacity_sum", "filters": {"capacity_group": "camas"}}))
    assert ok.data["value"] == 97036 and ok.data["unit"] == "camas"
    assert {"MIXED_TYPES", "NOT_AVAILABILITY", "FILTER_NORMALIZED"} <= set(ok.evidence.warnings)
    assert "nom_grupo_capacidad = 'CAMAS'" in ds.queries[-1]


async def test_municipality_group_uses_combined_key():
    rows = [{"municipio": "BOGOTÁ", "departamento": "Bogotá D.C", "value": "16193"}]
    ds = FakeDataset().on("GROUP BY municipio, departamento", rows)
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "capacity_sum", "group_by": "municipality", "top_n": 5,
                                                    "filters": {"capacity_group": "CAMAS"}}))
    assert env.data["groups"][0]["key"] == "BOGOTÁ · Bogotá D.C" and env.data["groups"][0]["department"] == "Bogotá D.C"
    assert "LIMIT 5" in ds.queries[-1] and env.evidence.complete


async def test_valle_del_cauca_warns_districts_are_separate():  # A-26
    ds = FakeDataset().on("count(DISTINCT", [{"value": "400"}])
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "provider_count",
                                                    "filters": {"department": "Valle del Cauca"}}))
    assert "departamento = 'Valle del cauca'" in ds.queries[-1]
    assert {"DISTRICT_AS_DEPARTMENT", "FILTER_NORMALIZED"} <= set(env.evidence.warnings)


async def test_cali_in_valle_resolves_to_the_district():
    ds = FakeDataset().on("count(DISTINCT", [{"value": "300"}])
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "provider_count",
                                                    "filters": {"department": "Valle", "municipality": "Cali"}}))
    assert "departamento = 'Cali'" in ds.queries[-1] and "municipio = 'CALI'" in ds.queries[-1]
    assert "DISTRICT_AS_DEPARTMENT" in env.evidence.warnings


async def test_homonym_municipality_without_department_is_ambiguous():  # A-04 / A-19
    ds = FakeDataset()
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "provider_count", "filters": {"municipality": "Armenia"}}))
    assert env.status == "ambiguous" and len(env.data["candidates"]) == 2 and ds.queries == []
    assert env.evidence is not None and env.trace.soql == ""


async def test_name_in_several_departments_asks_for_location_never_picks_first():  # A-04
    ds = FakeDataset()
    env = await _svc(ds).run("search_ips", _req({"name": "San José"}))
    assert env.status == "ambiguous" and env.data["field"] == "department"
    assert set(env.data["candidates"]) == {"Tolima", "Boyacá"} and ds.queries == []


async def test_search_with_location_filters_by_provider_codes_and_pages():  # A-03
    rows = [{"c_digo_prestador": "111", "c_digo_sede": "111", "n_mero_sede": f"0{i}",
             "nombre_prestador": "E.S.E. HOSPITAL SAN JOSÉ", "nom_sede_ips": f"SEDE {i}", "municipio": "MELGAR",
             "departamento": "Tolima", "naturaleza": "Pública"} for i in range(1, 4)]
    ds = FakeDataset().on("GROUP BY c_digo_prestador", rows)
    svc = _svc(ds)
    env = await svc.run("search_ips", _req({"name": "hospital san jose", "department": "Tolima", "limit": 2}))
    assert "c_digo_prestador IN ('111')" in ds.queries[-1] and "LIMIT 3" in ds.queries[-1]
    assert env.status == "ok" and [i["site_key"] for i in env.data["items"]] == ["111:111:01", "111:111:02"]
    assert env.data["items"][0]["level"] is None and env.next_cursor and not env.evidence.complete
    assert env.context_patch["last_result_site_keys"] == ["111:111:01", "111:111:02"]
    nxt = await svc.run("search_ips", _req({"name": "hospital san jose", "department": "Tolima", "limit": 2,
                                            "cursor": env.next_cursor}, call_id="c2"))
    assert "OFFSET 2" in ds.queries[-1] and nxt.status == "ok"


async def test_forged_cursor_is_invalid():
    env = await _svc(FakeDataset()).run("search_ips", _req({"department": "Tolima", "cursor": "abc"}))
    assert env.status == "invalid" and env.error.code == "INVALID_CURSOR"


async def test_unknown_field_is_rejected():  # R-23: closed lists
    env = await _svc(FakeDataset()).run("aggregate_ips", _req({"metric": "provider_count", "soql": "SELECT *"}))
    assert env.status == "invalid" and env.error.code == "INVALID_ARGS"


async def test_unavailable_is_never_empty():  # A-12 / A-18
    ds = FakeDataset().on("count(DISTINCT", unavailable("TIMEOUT"))
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "provider_count"}))
    assert env.status == "unavailable" and env.error.code == "TIMEOUT" and env.error.retryable
    assert env.data == {} and not env.evidence.complete


async def test_same_call_same_state_is_not_queried_twice():  # docs/08 section 5.5, A-16/A-17
    ds = FakeDataset().on("count(DISTINCT", [{"value": "9320"}])
    svc = _svc(ds)
    first = await svc.run("aggregate_ips", _req({"metric": "provider_count"}))
    again = await svc.run("aggregate_ips", _req({"metric": "provider_count"}))
    assert len(ds.queries) == 1 and again == first


async def test_force_live_bypasses_cache():  # A-24 "Reconsultar"
    ds = FakeDataset().on("count(DISTINCT", [{"value": "9320"}])
    await _svc(ds).run("aggregate_ips", _req({"metric": "provider_count"}, force_live=True))
    assert ds.bypass == [True]


async def test_details_null_quantity_is_unknown_not_zero():  # A-07
    ds = (FakeDataset()
          .on("LIMIT 1", [{"c_digo_prestador": "111", "c_digo_sede": "111", "n_mero_sede": "01",
                           "nombre_prestador": "X", "nom_sede_ips": "Y", "municipio": "MELGAR",
                           "departamento": "Tolima", "naturaleza": "Pública"}])
          .on("AS quantity", [{"nom_grupo_capacidad": "CAMAS", "nom_descripcion_capacidad": "Adultos"}]))
    env = await _svc(ds).run("get_ips_details", _req({"site_key": "111:111:01"}))
    assert env.data["capacities"] == [{"group": "CAMAS", "type": "Adultos", "quantity": None}]
    assert {"NULL_NOT_ZERO", "NOT_AVAILABILITY"} <= set(env.evidence.warnings) and len(env.traces) == 2
    assert "direcci_n" not in ds.queries[0]  # contact only on explicit request


async def test_correct_context_bumps_version_and_invalidates():  # A-09
    env = await _svc(FakeDataset()).run("correct_context", _req(
        {"target_turn_id": "t1", "expected_state_version": 3, "field": "municipality", "value": "Melgar"},
        state_version=3))
    assert env.status == "ok" and env.state_version == 4
    assert env.context_patch["confirmed_filters"] == {"department": "Tolima", "municipality": "MELGAR"}
    assert env.context_patch["last_evidence_refs"] == [] and env.context_patch["selected_site_keys"] == []
    assert env.data["resolved"] == "Tolima, MELGAR"


async def test_correct_context_rejects_stale_state():
    env = await _svc(FakeDataset()).run("correct_context", _req(
        {"target_turn_id": "t1", "expected_state_version": 1, "field": "nature", "value": "publica"}, state_version=2))
    assert env.status == "invalid" and env.error.code == "STATE_CONFLICT"


def test_literals_are_escaped():
    assert soql.where({"department": "O'Higgins"}) == "departamento = 'O''Higgins'"
    with pytest.raises(soql.SoqlError):
        soql.where({"password": "x"})
