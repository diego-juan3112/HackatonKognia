"""Tool declarations handed to the voice engines when minting a session (docs/08 section 3).

Hand-written, provider-neutral JSON Schema (no ``anyOf``/``$defs``, which
Gemini function declarations reject). ``tests/services/test_tool_specs.py``
keeps them in lock-step with the Pydantic models in ``models/ips.py``, which
are what the backend actually validates (R-23).
"""

from __future__ import annotations

from models.voice import ToolSpec

_NATURE = {"type": "string", "enum": ["Pública", "Privada", "Mixta"], "description": "Naturaleza jurídica"}
_LEVEL = {"type": "integer", "enum": [1, 2, 3],
          "description": "Nivel de atención registrado. Vacío en el 89% de las IPS: no lo infieras"}
_DEPT = {"type": "string", "description": "Departamento tal como lo dijo la persona (p. ej. «Antioquia», «Bogotá»)"}
_MUNI = {"type": "string", "description": "Municipio tal como lo dijo la persona; si hay homónimos, agrega department"}
_GROUP = {"type": "string", "description": "Grupo de capacidad: CAMAS, SALAS, CAMILLAS, CONSULTORIOS, AMBULANCIAS, "
                                           "SILLAS o UNIDAD MOVIL"}
_TYPE = {"type": "string", "description": "Tipo dentro del grupo, p. ej. «Adultos» en CAMAS"}

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="search_ips",
        description="Busca sedes de IPS por ubicación, nombre, naturaleza o nivel. Devuelve hasta `limit` sedes con "
                    "su site_key. Si la ubicación es ambigua responde 'ambiguous': pregunta, no elijas.",
        parameters={"type": "object", "properties": {
            "department": _DEPT, "municipality": _MUNI,
            "name": {"type": "string", "description": "Nombre del prestador o de la sede, p. ej. «San José»"},
            "nature": _NATURE, "level": _LEVEL,
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Máximo de sedes (5 por omisión)"},
            "cursor": {"type": "string", "description": "next_cursor de una búsqueda anterior, para la página siguiente"},
        }},
    ),
    ToolSpec(
        name="get_ips_details",
        description="Detalle de una sede y su capacidad instalada por grupo y tipo. Contacto solo si la persona lo "
                    "pide explícitamente.",
        parameters={"type": "object", "properties": {
            "site_key": {"type": "string", "description": "site_key devuelto por search_ips"},
            "capacity_group": _GROUP, "capacity_type": _TYPE,
            "include_contact": {"type": "boolean", "description": "true solo si la persona pidió dirección o teléfono"},
        }, "required": ["site_key"]},
    ),
    ToolSpec(
        name="aggregate_ips",
        description="Cuenta prestadores (provider_count), códigos de sede (site_count) o suma capacidad instalada "
                    "(capacity_sum, exige capacity_group). Totales exactos de la fuente, opcionalmente agrupados.",
        parameters={"type": "object", "properties": {
            "metric": {"type": "string", "enum": ["provider_count", "site_count", "capacity_sum"]},
            "filters": {"type": "object", "properties": {
                "department": _DEPT, "municipality": _MUNI,
                "name": {"type": "string", "description": "Nombre del prestador"},
                "nature": _NATURE, "level": _LEVEL, "capacity_group": _GROUP, "capacity_type": _TYPE,
            }},
            "group_by": {"type": "string", "enum": ["department", "municipality", "nature", "level"]},
            "order": {"type": "string", "enum": ["desc", "asc"]},
            "top_n": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Cuántos grupos devolver"},
        }, "required": ["metric"]},
    ),
    ToolSpec(
        name="compare_ips",
        description="Compara la capacidad instalada de 2 o 3 sedes ya resueltas, del mismo grupo y tipo.",
        parameters={"type": "object", "properties": {
            "site_keys": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
            "capacity_group": _GROUP, "capacity_type": _TYPE,
        }, "required": ["site_keys", "capacity_group"]},
    ),
    ToolSpec(
        name="correct_context",
        description="Aplica una corrección explícita de la persona («no, dije Melgar»). Después vuelve a consultar "
                    "con el valor corregido.",
        parameters={"type": "object", "properties": {
            "target_turn_id": {"type": "string", "description": "Turno que se corrige"},
            "expected_state_version": {"type": "integer", "description": "state_version vigente del contexto"},
            "field": {"type": "string", "enum": ["department", "municipality", "name", "nature", "level", "site_key"]},
            "value": {"type": "string", "description": "Valor corregido tal como lo dijo la persona"},
        }, "required": ["target_turn_id", "expected_state_version", "field", "value"]},
    ),
]
