"""Contract .3 tools (docs/09 section 4): validate, profile, compare, explain -- against FakeDataset (R-16)."""

from __future__ import annotations

from tests.doubles.fake_dataset import FakeDataset
from tests.services.test_ips_tools import _req, _svc

_SITE = {"c_digo_prestador": "333", "c_digo_sede": "333", "n_mero_sede": "01", "nombre_prestador": "CLINICA LAS AMERICAS",
         "nom_sede_ips": "SEDE PRINCIPAL", "municipio": "MEDELLÍN", "departamento": "Antioquia",
         "naturaleza": "Privada", "num_nivel_atencion": "3"}


# -- search_ips with installed capacity -------------------------------------------------

async def test_search_by_capacity_lists_sites_that_have_it_never_availability():
    rows = [{**_SITE, "municipio": "MELGAR", "departamento": "Tolima", "quantity": "2"}]
    ds = FakeDataset().on("GROUP BY c_digo_prestador", rows)
    env = await _svc(ds).run("search_ips", _req({"municipality": "Melgar", "capacity_group": "consultorios",
                                                 "capacity_type": "urgencias"}))
    q = ds.queries[-1]
    assert "nom_grupo_capacidad = 'CONSULTORIOS'" in q and "nom_descripcion_capacidad = 'Urgencias'" in q
    assert "sum(num_cantidad_capacidad_instalada) AS quantity" in q and "municipio = 'MELGAR'" in q
    assert env.status == "ok" and env.data["items"][0]["quantity"] == 2
    assert "NOT_AVAILABILITY" in env.evidence.warnings and "MIXED_TYPES" not in env.evidence.warnings
    assert "no significa que esté abierta" in env.for_model and "capacidad registrada 2" in env.for_model


async def test_search_without_capacity_keeps_the_same_soql():  # cache shared with older clients
    ds = FakeDataset().on("GROUP BY c_digo_prestador", [])
    await _svc(ds).run("search_ips", _req({"department": "Tolima"}))
    assert "quantity" not in ds.queries[-1]


# -- verify_registration -----------------------------------------------------------------

async def test_verify_registered_provider_with_attributes():
    ds = FakeDataset().on("c_digo_prestador = '333'", [_SITE, {**_SITE, "n_mero_sede": "02"}])
    env = await _svc(ds).run("verify_registration", _req({"name": "Clinica las Americas", "municipality": "Medellín"}))
    d = env.data
    assert env.status == "ok" and d["registered"] is True and d["provider_code"] == "333"
    assert d["nature"] == "Privada" and d["levels"] == [3] and d["site_count"] == 2
    assert d["municipalities"] == ["MEDELLÍN (Antioquia)"] and "LIMIT 21" in ds.queries[-1]
    assert "SÍ está registrada" in env.for_model


async def test_verify_unknown_name_is_empty_never_does_not_exist():
    ds = FakeDataset()
    env = await _svc(ds).run("verify_registration", _req({"name": "Clínica Inventada Zeta", "department": "Tolima"}))
    assert env.status == "empty" and env.data["registered"] is False and ds.queries == []
    assert "no aparece registrada con ese nombre en el corte de 2022" in env.for_model
    assert "no prueba que no exista" in env.for_model


async def test_verify_name_in_several_departments_asks_never_picks_first():
    ds = FakeDataset()
    env = await _svc(ds).run("verify_registration", _req({"name": "San José"}))
    assert env.status == "ambiguous" and set(env.data["candidates"]) == {"Tolima", "Boyacá"} and ds.queries == []


async def test_verify_needs_exactly_one_identifier():
    env = await _svc(FakeDataset()).run("verify_registration", _req({"name": "x y", "provider_code": "333"}))
    assert env.status == "invalid" and env.error.code == "INVALID_ARGS"


async def test_verify_unknown_code_is_empty_after_a_live_query():
    ds = FakeDataset().on("c_digo_prestador = '999'", [])
    env = await _svc(ds).run("verify_registration", _req({"provider_code": "999"}))
    assert env.status == "empty" and len(ds.queries) == 1 and "no prueba que no exista" in env.for_model


# -- area_profile --------------------------------------------------------------------------

def _profile_ds() -> FakeDataset:
    return (FakeDataset()
            .on("GROUP BY naturaleza", [{"naturaleza": "Privada", "value": "7"}, {"naturaleza": "Pública", "value": "2"}])
            .on("GROUP BY num_nivel_atencion", [{"value": "8"}, {"num_nivel_atencion": "1", "value": "1"}])
            .on("count(DISTINCT c_digo_sede)", [{"value": "12"}])
            .on("'CAMAS'", [{"value": "40"}])
            .on("'AMBULANCIAS'", [{"value": "3"}])
            .on("'Urgencias'", [{}]))  # sum of nothing: no value -> not registered, not zero


async def test_area_profile_runs_all_queries_and_derives_shares_in_python():
    ds = _profile_ds()
    env = await _svc(ds).run("area_profile", _req({"municipality": "Melgar"}))
    d = env.data
    assert env.status == "ok" and len(ds.queries) == 6 and len(env.traces) == 6
    assert all("municipio = 'MELGAR'" in q for q in ds.queries)
    assert d["providers"] == 9 and d["by_nature"][0] == {"key": "Privada", "value": 7, "share_pct": 78}
    assert d["by_level"][0]["label"] == "sin nivel registrado" and d["derived"]["level_registered_pct"] == 11
    assert d["beds"] == 40 and d["ambulances"] == 3 and d["emergency_rooms"] is None
    assert d["derived"]["beds_per_provider"] == 4.4 and d["area"] == "Melgar (Tolima)"
    assert {"DERIVED_FROM_SOURCE", "NULL_NOT_ZERO", "NOT_AVAILABILITY"} <= set(env.evidence.warnings)
    assert "Privada 7 (78%)" in env.for_model and "Calculado a partir de la fuente" in env.for_model
    assert len(env.for_model) <= 700


async def test_area_profile_shares_soql_with_aggregate_ips():  # same SoQL -> 60 s cache hit
    ds = _profile_ds()
    svc = _svc(ds)
    await svc.run("area_profile", _req({"department": "Antioquia"}))
    await svc.run("aggregate_ips", _req({"metric": "capacity_sum", "filters": {"department": "Antioquia",
                                                                              "capacity_group": "CAMAS"}}, "c2"))
    assert ds.queries[-1] in ds.queries[:-1]


async def test_area_profile_needs_a_place():
    env = await _svc(FakeDataset()).run("area_profile", _req({}))
    assert env.status == "invalid"


# -- compare_areas ---------------------------------------------------------------------------

async def test_compare_areas_differences_and_ratio_in_python():
    ds = (FakeDataset().on("departamento = 'Antioquia'", [{"value": "837"}])
          .on("departamento = 'Santander'", [{"value": "597"}]))
    env = await _svc(ds).run("compare_areas", _req({"metric": "provider_count", "areas": [
        {"department": "Santander"}, {"department": "Antioquia"}]}))
    d = env.data
    assert env.status == "ok" and d["highest"] == "Antioquia" and len(ds.queries) == 2
    assert d["comparisons"] == [{"higher": "Antioquia", "lower": "Santander", "equal": False, "difference": 240,
                                 "ratio": 1.4}]
    assert "Antioquia tiene 240 más que Santander (1,4 veces)" in env.for_model
    assert "NOT_PER_CAPITA" in env.evidence.warnings


async def test_compare_areas_ambiguous_area_is_ambiguous():
    env = await _svc(FakeDataset()).run("compare_areas", _req({"metric": "provider_count", "areas": [
        {"municipality": "Armenia"}, {"department": "Tolima"}]}))
    assert env.status == "ambiguous" and env.data["area_index"] == 0


async def test_compare_areas_capacity_needs_group_and_max_three():
    svc = _svc(FakeDataset())
    env = await svc.run("compare_areas", _req({"metric": "capacity_sum", "areas": [
        {"department": "Tolima"}, {"department": "Antioquia"}]}))
    assert env.status == "invalid"
    env = await svc.run("compare_areas", _req({"metric": "provider_count", "areas": [
        {"department": d} for d in ("Tolima", "Antioquia", "Santander", "Boyacá")]}, "c2"))
    assert env.status == "invalid" and env.error.code == "INVALID_ARGS"


# -- dataset_info -------------------------------------------------------------------------------

async def test_dataset_info_is_static_and_explains_limits():
    ds = FakeDataset()
    env = await _svc(ds).run("dataset_info", _req({}))
    assert env.status == "ok" and ds.queries == [] and env.trace.soql == ""
    assert "citas ni agendamiento" in env.data["not_contains"] and "CAMAS" in env.data["contents"]["capacity_groups"]
    assert "NO contiene" in env.for_model and "Puedo:" in env.for_model
    limits = await _svc(ds).run("dataset_info", _req({"topic": "limits"}))
    assert "capabilities" not in limits.data and len(limits.for_model) <= 600
