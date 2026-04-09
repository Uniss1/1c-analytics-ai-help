"""Deterministic query builder: structured params → 1C query.

Takes the JSON produced by param_extractor and builds a valid
1C:Enterprise query string. No LLM involved — pure template logic.
"""


def _date_field(register_metadata: dict) -> str:
    """Find the date dimension field name."""
    for dim in register_metadata.get("dimensions", []):
        if dim["data_type"] == "Дата":
            return dim["name"]
    return "Период_Показателя"


def build_query(params: dict, register_metadata: dict) -> dict:
    """Build 1C query from structured parameters.

    Args:
        params: extracted params from param_extractor (resource, filters, period, group_by, etc.)
        register_metadata: register metadata with name, dimensions, resources

    Returns: {"query": str, "params": dict}
    """
    register_name = register_metadata["name"]
    resource = params.get("resource", "Сумма")
    group_by = params.get("group_by", [])
    order_by = params.get("order_by", "desc")
    limit = params.get("limit", 1000)
    filters = params.get("filters", {})
    period = params.get("period", {})

    date_field = _date_field(register_metadata)
    dim_names = {d["name"] for d in register_metadata.get("dimensions", [])}

    # Build WHERE conditions and query params
    conditions = []
    query_params = {}

    # Period filter
    if period.get("from"):
        conditions.append(f"{date_field} >= &Начало")
        query_params["Начало"] = period["from"]
    if period.get("to"):
        conditions.append(f"{date_field} <= &Конец")
        query_params["Конец"] = period["to"]

    # Dimension filters
    for dim_name, value in filters.items():
        if value is not None and dim_name in dim_names:
            param_key = dim_name.replace(" ", "_")
            conditions.append(f"{dim_name} = &{param_key}")
            query_params[param_key] = value

    # SELECT clause
    if group_by:
        select_fields = group_by + [f"СУММА({resource}) КАК Значение"]
    else:
        select_fields = [f"СУММА({resource}) КАК Значение"]

    select_clause = ",\n    ".join(select_fields)

    # WHERE clause
    where_clause = ""
    if conditions:
        where_clause = "\nГДЕ\n    " + "\n    И ".join(conditions)

    # GROUP BY
    group_clause = ""
    if group_by:
        group_clause = "\nСГРУППИРОВАТЬ ПО " + ", ".join(group_by)

    # ORDER BY
    order_dir = "УБЫВ" if order_by == "desc" else "ВОЗР"
    order_clause = f"\nУПОРЯДОЧИТЬ ПО Значение {order_dir}"

    query = f"""ВЫБРАТЬ ПЕРВЫЕ {limit}
    {select_clause}
ИЗ
    {register_name}{where_clause}{group_clause}{order_clause}"""

    return {"query": query, "params": query_params}
