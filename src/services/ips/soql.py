"""SoQL builder with a closed list of columns and functions (D-13, R-23).

The voice model never writes SoQL: it sends typed arguments, services/ips
resolves them against the lexicon, and only this module turns resolved
values into a query. Literals are escaped by doubling single quotes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# Canonical field -> Socrata column (docs/09 section 1, "Mapeo de campos").
COLUMNS: dict[str, str] = {
    "department": "departamento",
    "municipality": "municipio",
    "provider_code": "c_digo_prestador",
    "provider_name": "nombre_prestador",
    "site_code": "c_digo_sede",
    "site_number": "n_mero_sede",
    "site_name": "nom_sede_ips",
    "nature": "naturaleza",
    "level": "num_nivel_atencion",
    "capacity_group": "nom_grupo_capacidad",
    "capacity_type": "nom_descripcion_capacidad",
    "quantity": "num_cantidad_capacidad_instalada",
    "address": "direcci_n",
    "email": "email",
    "phone": "tel_fono",
    "manager": "gerente",
}
_ALLOWED_COLUMNS = frozenset(COLUMNS.values())

SITE_COLUMNS = ["provider_code", "site_code", "site_number", "provider_name", "site_name",
                "municipality", "department", "nature", "level"]
CONTACT_COLUMNS = ["address", "phone", "email", "manager"]


class SoqlError(ValueError):
    """Raised when a caller asks for something outside the closed lists (a bug, not user input)."""


def col(field: str) -> str:
    try:
        return COLUMNS[field]
    except KeyError:
        raise SoqlError(f"field not allowed: {field}") from None


def lit(value: str | int) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def where(filters: Mapping[str, object], provider_codes: Iterable[str] | None = None) -> str:
    """Equality filters on allowed fields, plus an optional provider-code IN list."""
    clauses: list[str] = []
    for field, value in filters.items():
        if value is None:
            continue
        clauses.append(f"{col(field)} = {lit(value)}")  # type: ignore[arg-type]
    codes = list(provider_codes or [])
    if codes:
        clauses.append(f"{col('provider_code')} IN ({', '.join(lit(c) for c in codes)})")
    return " AND ".join(clauses)


def site_key_clause(provider_code: str, site_code: str, site_number: str) -> str:
    return (
        f"{col('provider_code')} = {lit(provider_code)} AND {col('site_code')} = {lit(site_code)} "
        f"AND {col('site_number')} = {lit(site_number)}"
    )


def _assemble(select: str, where_sql: str, group: str = "", order: str = "", limit: int | None = None,
              offset: int | None = None) -> str:
    parts = [f"SELECT {select}"]
    if where_sql:
        parts.append(f"WHERE {where_sql}")
    if group:
        parts.append(f"GROUP BY {group}")
    if order:
        parts.append(f"ORDER BY {order}")
    if limit is not None:
        parts.append(f"LIMIT {int(limit)}")
    if offset:
        parts.append(f"OFFSET {int(offset)}")
    return " ".join(parts)


METRIC_EXPR = {
    "provider_count": f"count(DISTINCT {COLUMNS['provider_code']})",
    "site_count": f"count(DISTINCT {COLUMNS['site_code']})",
    "capacity_sum": f"sum({COLUMNS['quantity']})",
}
GROUP_COLUMNS = {
    "department": ["department"],
    "municipality": ["municipality", "department"],
    "nature": ["nature"],
    "level": ["level"],
}


def aggregate(metric: str, where_sql: str, group_by: str | None = None, order: str = "desc",
              limit: int | None = None) -> str:
    expr = METRIC_EXPR[metric]
    if not group_by:
        return _assemble(f"{expr} AS value", where_sql)
    cols = ", ".join(col(f) for f in GROUP_COLUMNS[group_by])
    direction = "DESC" if order == "desc" else "ASC"
    return _assemble(f"{cols}, {expr} AS value", where_sql, group=cols, order=f"value {direction}", limit=limit)


def search_sites(where_sql: str, limit: int, offset: int = 0, with_quantity: bool = False) -> str:
    """Sites (grouped so capacity rows do not repeat). ``with_quantity`` adds the summed capacity
    of the filtered group/type per site (search_ips with a capacity filter, contract .3)."""
    cols = ", ".join(col(f) for f in SITE_COLUMNS)
    select = cols + (f", sum({col('quantity')}) AS quantity" if with_quantity else "")
    order = f"{col('provider_name')}, {col('site_number')}, {col('site_code')}"
    return _assemble(select, where_sql, group=cols, order=order, limit=limit, offset=offset)


def site_info(key_sql: str, include_contact: bool) -> str:
    fields = SITE_COLUMNS + (CONTACT_COLUMNS if include_contact else [])
    cols = ", ".join(col(f) for f in fields)
    return _assemble(cols, key_sql, group=cols, limit=1)


def site_capacities(key_sql: str) -> str:
    cols = f"{col('capacity_group')}, {col('capacity_type')}"
    return _assemble(f"{cols}, sum({col('quantity')}) AS quantity", key_sql, group=cols, order=cols)


def compare_sites(keys_sql: list[str], filters_sql: str) -> str:
    any_site = " OR ".join(f"({k})" for k in keys_sql)
    where_sql = f"({any_site})" + (f" AND {filters_sql}" if filters_sql else "")
    cols = f"{col('provider_code')}, {col('site_code')}, {col('site_number')}, {col('site_name')}"
    return _assemble(f"{cols}, sum({col('quantity')}) AS quantity", where_sql, group=cols)


def brief_counts() -> str:
    return (f"SELECT count(*) AS rows, count(DISTINCT {col('provider_code')}) AS providers, "
            f"count(DISTINCT {col('site_code')}) AS site_codes")


def assert_safe(soql: str) -> None:
    """Defence in depth: every identifier-looking column in the query must be allowed."""
    lowered = soql.lower()
    for forbidden in (";", "--", "/*", " delete ", " update ", " insert ", " drop "):
        if forbidden in lowered:
            raise SoqlError(f"forbidden token in query: {forbidden.strip()}")
