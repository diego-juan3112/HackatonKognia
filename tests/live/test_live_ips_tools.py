"""Golden numbers and traps of docs/09 section 9, against the live source."""

from __future__ import annotations

import uuid

from models.ips import ToolRequest

GOLDEN_NATURE = {"Privada": 8308, "Pública": 998, "Mixta": 14}
GOLDEN_LEVEL = {None: 8325, "1": 853, "2": 113, "3": 29}


def _req(args: dict, state_version: int = 0) -> ToolRequest:
    # force_live: every probe must reach datos.gov.co, never the in-memory cache.
    return ToolRequest(tool_call_id=str(uuid.uuid4()), args=args, force_live=True,
                       context={"conversation_id": "live", "turn_id": "t1", "state_version": state_version})


async def test_provider_count_is_9320(live_tools):
    env = await live_tools.run("aggregate_ips", _req({"metric": "provider_count"}))
    assert env.status == "ok", env.error
    assert env.data["value"] == 9320
    assert env.trace.cache_status == "live" and env.trace.soql and env.evidence.query_fingerprint


async def test_beds_sum_is_97036(live_tools):
    env = await live_tools.run("aggregate_ips", _req({"metric": "capacity_sum",
                                                      "filters": {"capacity_group": "CAMAS"}}))
    assert env.status == "ok", env.error
    assert env.data["value"] == 97036 and "NOT_AVAILABILITY" in env.evidence.warnings


async def test_providers_by_nature(live_tools):
    env = await live_tools.run("aggregate_ips", _req({"metric": "provider_count", "group_by": "nature"}))
    assert env.status == "ok", env.error
    assert {g["key"]: g["value"] for g in env.data["groups"]} == GOLDEN_NATURE


async def test_providers_by_level_keeps_the_null_group(live_tools):
    env = await live_tools.run("aggregate_ips", _req({"metric": "provider_count", "group_by": "level"}))
    assert env.status == "ok", env.error
    groups = {g["key"]: g["value"] for g in env.data["groups"]}
    assert groups == GOLDEN_LEVEL
    null = next(g for g in env.data["groups"] if g["key"] is None)
    assert null["label"] == "sin nivel registrado" and "LEVEL_MISSING_MOSTLY" in env.evidence.warnings


async def test_antioquia_public_search_returns_site_keys_and_a_second_page(live_tools):
    args = {"department": "Antioquia", "nature": "Pública", "limit": 5}
    first = await live_tools.run("search_ips", _req(args))
    assert first.status == "ok", first.error
    keys = [i["site_key"] for i in first.data["items"]]
    assert len(keys) == 5 and all(k.count(":") == 2 for k in keys)
    assert all(i["nature"] == "Pública" and i["department"] == "Antioquia" for i in first.data["items"])
    assert first.next_cursor and "PARTIAL_RESULT" in first.evidence.warnings

    second = await live_tools.run("search_ips", _req({**args, "cursor": first.next_cursor}))
    assert second.status == "ok", second.error
    keys2 = [i["site_key"] for i in second.data["items"]]
    assert keys2 and not set(keys) & set(keys2)


async def test_homonym_armenia_is_ambiguous(live_tools):
    env = await live_tools.run("aggregate_ips", _req({"metric": "provider_count",
                                                      "filters": {"municipality": "Armenia"}}))
    assert env.status == "ambiguous"
    assert len(env.data["candidates"]) >= 2


async def test_valle_del_cauca_warns_district_as_department(live_tools):
    env = await live_tools.run("aggregate_ips", _req({"metric": "provider_count",
                                                      "filters": {"department": "Valle del Cauca"}}))
    assert env.status == "ok", env.error
    assert "DISTRICT_AS_DEPARTMENT" in env.evidence.warnings
    assert env.data["value"] > 0


async def test_details_of_a_searched_site_return_capacities(live_tools):
    search = await live_tools.run("search_ips", _req({"department": "Antioquia", "nature": "Pública", "limit": 5}))
    assert search.status == "ok", search.error
    site_key = search.data["items"][0]["site_key"]
    env = await live_tools.run("get_ips_details", _req({"site_key": site_key}))
    assert env.status == "ok", env.error
    assert env.data["site"]["site_key"] == site_key
    caps = env.data["capacities"]
    assert caps and all(c["group"] for c in caps)
    assert "contact" not in env.data["site"]  # no contact data unless asked (docs/09 section 10)
