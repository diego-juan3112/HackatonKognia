"""Anti-hallucination layers (R-22): grounded ``for_model`` text and the figure verifier."""

from __future__ import annotations

from models.ips import ToolRequest
from services.ips.lexicon import Lexicon
from services.ips.tools import IpsToolService
from services.ips.verify import numbers_in_text, verify
from tests.doubles.fake_dataset import FakeDataset, unavailable
from tests.fixtures.lexicon_small import LEXICON


def _svc(ds: FakeDataset) -> IpsToolService:
    return IpsToolService(ds, Lexicon(LEXICON), dataset_id="s2ru-bqt6",
                          source_url="https://www.datos.gov.co/resource/s2ru-bqt6.json", cursor_key=b"k" * 32)


def _req(args: dict, call_id: str = "c1") -> ToolRequest:
    return ToolRequest(tool_call_id=call_id, args=args, context={"state_version": 0})


async def test_for_model_states_exact_figure_unit_and_caveats():
    ds = FakeDataset().on("sum(", [{"value": "97036"}])
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "capacity_sum", "filters": {"capacity_group": "CAMAS"}}))
    text = env.for_model
    assert "97.036 camas" in text and "corte 5 de noviembre de 2022" in text
    assert "no disponibilidad actual" in text and "no se sabe" in text and "grupo=CAMAS" in text


async def test_for_model_groups_name_the_null_level():
    ds = FakeDataset().on("GROUP BY num_nivel_atencion", [{"value": "8325"}, {"num_nivel_atencion": "1",
                                                                              "value": "853"}])
    env = await _svc(ds).run("aggregate_ips", _req({"metric": "provider_count", "group_by": "level"}))
    assert "sin nivel registrado: 8.325" in env.for_model and "nivel 1: 853" in env.for_model


async def test_for_model_never_invites_an_answer_when_unavailable_or_ambiguous():
    down = await _svc(FakeDataset().on("count(", unavailable())).run(
        "aggregate_ips", _req({"metric": "provider_count"}))
    assert "No respondas de memoria" in down.for_model
    amb = await _svc(FakeDataset()).run(
        "aggregate_ips", _req({"metric": "provider_count", "filters": {"municipality": "Armenia"}}, "c2"))
    assert "No elijas tú ni des cifras" in amb.for_model and "Quindío" in amb.for_model


async def test_for_model_marks_missing_level_as_not_registered():
    rows = [{"c_digo_prestador": "333", "c_digo_sede": "333", "n_mero_sede": "01", "nombre_prestador": "CLINICA",
             "nom_sede_ips": "SEDE", "municipio": "MEDELLÍN", "departamento": "Antioquia", "naturaleza": "Privada"}]
    env = await _svc(FakeDataset().on("GROUP BY c_digo_prestador", rows)).run(
        "search_ips", _req({"department": "Antioquia", "nature": "Privada"}))
    assert "nivel no registrado" in env.for_model and "site_key 333:333:01" in env.for_model


async def test_for_model_is_compact_at_most_three_rows():
    rows = [{"municipio": m, "departamento": "D", "value": str(v)} for m, v in
            [("A", 50), ("B", 40), ("C", 30), ("D", 20), ("E", 10)]]
    env = await _svc(FakeDataset().on("GROUP BY municipio", rows)).run("aggregate_ips", _req(
        {"metric": "capacity_sum", "group_by": "municipality", "top_n": 5, "filters": {"capacity_group": "CAMAS"}}))
    assert "A (D): 50" in env.for_model and "C (D): 30" in env.for_model and "D: 20" not in env.for_model
    assert "(+2 en pantalla)" in env.for_model and "SELECT" not in env.for_model and len(env.for_model) < 600
    assert len(env.data["groups"]) == 5  # the browser still gets everything


async def test_for_model_district_is_not_repeated():
    rows = [{"municipio": "CALI", "departamento": "Cali", "value": "5876"},
            {"municipio": "BOGOTÁ", "departamento": "Bogotá D.C", "value": "16193"}]
    env = await _svc(FakeDataset().on("GROUP BY municipio", rows)).run("aggregate_ips", _req(
        {"metric": "capacity_sum", "group_by": "municipality", "top_n": 2, "filters": {"capacity_group": "CAMAS"}}))
    assert "Cali: 5.876" in env.for_model and "Bogotá: 16.193" in env.for_model  # 'bogota' vs 'bogota dc'
    assert env.data["groups"][0]["key"] == "CALI · Cali"  # the browser contract is unchanged


async def test_prefetch_uses_the_exact_tool_queries():
    ds = (FakeDataset().on("GROUP BY", [{"naturaleza": "Privada", "value": "1"}])
          .on("AS value", [{"value": "9320"}]))
    svc = _svc(ds)
    assert await svc.prefetch() == len(IpsToolService.LIKELY)
    warmed = set(ds.queries)
    await svc.run("aggregate_ips", _req({"metric": "provider_count", "group_by": "nature"}, "q1"))
    assert ds.queries[-1] in warmed  # same SoQL -> the 60 s cache in SocrataClient hits


async def test_for_model_invalid_says_the_source_did_answer():  # bench 2026-10-09
    env = await _svc(FakeDataset()).run("aggregate_ips", _req({"metric": "capacity_sum"}, "inv"))
    assert env.status == "invalid" and "La fuente SÍ respondió" in env.for_model
    assert "No digas que la fuente falló" in env.for_model


def test_verifier_flags_invented_figures():
    evidence = [{"value": 9320, "unit": "prestadores"}, {"groups": [{"key": "Pública", "value": 998}]}]
    ok = verify("Hay 9.320 prestadores, con corte a noviembre de 2022; 998 son públicos.", evidence)
    assert ok["grounded"] and ok["numbers"] == [9320, 998]
    bad = verify("Hay 9.320 prestadores y unas 15.000 camas disponibles.", evidence)
    assert not bad["grounded"] and bad["unsupported"] == [15000]
    assert "15.000" in bad["correction"] and "Corrígete" in bad["correction"] and ok["correction"] is None


def test_number_parsing_handles_colombian_formats_and_ignores_small_numbers():
    assert numbers_in_text("97.036 camas, 10 921 sedes, 3 resultados, 5 de noviembre de 2022") == [97036, 10921]
    assert numbers_in_text("1.234,5 metros") == [1234.5]
