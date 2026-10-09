"""Tool declarations handed to the voice engines when minting a session (docs/08 section 3).

Hand-written, provider-neutral JSON Schema (no ``anyOf``/``$defs``, which
Gemini function declarations reject; string enums only). Kept SHORT on purpose:
fewer input tokens, faster tool decision (latency task, 2026-10-09). The rules
live in the instructions; the backend validates everything anyway (R-23).
``tests/services/test_session_and_specs.py`` keeps them in lock-step with the
Pydantic models in ``models/ips.py``.
"""

from __future__ import annotations

from models.voice import ToolSpec

_S = {"type": "string"}
_NATURE = {"type": "string", "enum": ["Pública", "Privada", "Mixta"]}
_LEVEL = {"type": "integer", "minimum": 1, "maximum": 3}
_GROUP = {"type": "string", "description": "CAMAS, SALAS, CAMILLAS, CONSULTORIOS, AMBULANCIAS, SILLAS, UNIDAD MOVIL"}

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="search_ips",
        description="Lista sedes de IPS por ubicación, nombre, naturaleza o nivel.",
        parameters={"type": "object", "properties": {
            "department": _S, "municipality": _S, "name": _S, "nature": _NATURE, "level": _LEVEL,
            "limit": {"type": "integer", "minimum": 1, "maximum": 20}, "cursor": _S,
        }},
    ),
    ToolSpec(
        name="get_ips_details",
        description="Detalle y capacidad instalada de una sede (site_key de search_ips).",
        parameters={"type": "object", "properties": {
            "site_key": _S, "capacity_group": _GROUP, "capacity_type": _S, "include_contact": {"type": "boolean"},
        }, "required": ["site_key"]},
    ),
    ToolSpec(
        name="aggregate_ips",
        description="Cuenta IPS (provider_count) o códigos de sede (site_count), o suma capacidad (capacity_sum, "
                    "exige capacity_group). Opcional: agrupar.",
        parameters={"type": "object", "properties": {
            "metric": {"type": "string", "enum": ["provider_count", "site_count", "capacity_sum"]},
            "filters": {"type": "object", "properties": {
                "department": _S, "municipality": _S, "name": _S, "nature": _NATURE, "level": _LEVEL,
                "capacity_group": _GROUP, "capacity_type": _S,
            }},
            "group_by": {"type": "string", "enum": ["department", "municipality", "nature", "level"]},
            "order": {"type": "string", "enum": ["desc", "asc"]},
            "top_n": {"type": "integer", "minimum": 1, "maximum": 10},
        }, "required": ["metric"]},
    ),
    ToolSpec(
        name="compare_ips",
        description="Compara la capacidad de 2 o 3 sedes del mismo grupo.",
        parameters={"type": "object", "properties": {
            "site_keys": {"type": "array", "items": _S, "minItems": 2, "maxItems": 3},
            "capacity_group": _GROUP, "capacity_type": _S,
        }, "required": ["site_keys", "capacity_group"]},
    ),
    ToolSpec(
        name="correct_context",
        description="Aplica una corrección explícita de la persona; luego vuelve a consultar.",
        parameters={"type": "object", "properties": {
            "target_turn_id": _S, "expected_state_version": {"type": "integer"},
            "field": {"type": "string", "enum": ["department", "municipality", "name", "nature", "level", "site_key"]},
            "value": _S,
        }, "required": ["target_turn_id", "expected_state_version", "field", "value"]},
    ),
]
