"""Pre-built query templates for common dashboard questions.

Templates use WHERE-based filtering (not virtual table parameters),
matching the actual 1C register structure. Each template is built
dynamically from register metadata.
"""

import re

from .date_parser import parse_period

_TOP_N_RE = re.compile(r"(?:топ|top)[\s-]*(\d+)", re.IGNORECASE)


def _resource_name(register_metadata: dict) -> str:
    """Pick the primary resource (Сумма by default)."""
    resources = register_metadata.get("resources", [])
    if not resources:
        return "Сумма"
    # Prefer Сумма, then Выручка, then first available
    for preferred in ("Сумма", "Выручка"):
        for r in resources:
            if r["name"] == preferred:
                return preferred
    return resources[0]["name"]


def _register_name(register_metadata: dict) -> str:
    return register_metadata.get("name", "")


def _date_field(register_metadata: dict) -> str:
    """Find the date dimension field name."""
    for dim in register_metadata.get("dimensions", []):
        if dim["data_type"] == "Дата":
            return dim["name"]
    return "Период_Показателя"


def _grouping_dimension(register_metadata: dict, question: str) -> str | None:
    """Find a dimension to group by, based on the question text."""
    q_lower = question.lower()
    dims = register_metadata.get("dimensions", [])

    # Map question keywords to dimension names
    dim_hints = {
        "подразделени": "Подразделение",
        "дзо": "ДЗО",
        "организаци": "ДЗО",
        "компани": "ДЗО",
        "показател": "Показатель",
        "стат": "СтатьяЗатрат",
        "сценари": "Сценарий",
        "месяц": "Месяц",
        "контур": "КонтурПоказателя",
    }

    dim_names = {d["name"] for d in dims}
    for hint, dim_name in dim_hints.items():
        if hint in q_lower and dim_name in dim_names:
            return dim_name

    # Fallback: first string dimension that's not a filter field
    skip = {_date_field(register_metadata), "Масштаб", "Ед_изм", "Показатель_номер"}
    for dim in dims:
        if dim["data_type"] == "Строка" and dim["name"] not in skip:
            return dim["name"]

    return None


def _build_where(register_metadata: dict, question: str, dates: dict | None) -> tuple[str, dict]:
    """Build WHERE clause and params from question context."""
    conditions = []
    params = {}
    date_field = _date_field(register_metadata)

    # Date filter
    if dates:
        if dates.get("Начало"):
            conditions.append(f"{date_field} >= &Начало")
            params["Начало"] = dates["Начало"]
        if dates.get("Конец"):
            conditions.append(f"{date_field} <= &Конец")
            params["Конец"] = dates["Конец"]

    # Scenario filter: default to "Факт" unless question mentions otherwise
    q_lower = question.lower()
    dims = {d["name"] for d in register_metadata.get("dimensions", [])}
    if "Сценарий" in dims:
        if "прогноз" in q_lower:
            conditions.append("Сценарий = &Сценарий")
            params["Сценарий"] = "Прогноз"
        elif "план" in q_lower:
            conditions.append("Сценарий = &Сценарий")
            params["Сценарий"] = "План"
        else:
            conditions.append("Сценарий = &Сценарий")
            params["Сценарий"] = "Факт"

    # Contour filter: default to "свод"
    if "КонтурПоказателя" in dims:
        if "детал" in q_lower:
            conditions.append("КонтурПоказателя = &Контур")
            params["Контур"] = "детализация"
        else:
            conditions.append("КонтурПоказателя = &Контур")
            params["Контур"] = "свод"

    where = ""
    if conditions:
        where = "\nГДЕ\n    " + "\n    И ".join(conditions)

    return where, params


def _try_aggregate(question: str, register_metadata: dict) -> dict | None:
    """Template: aggregate (SUM) a resource, optionally filtered by period."""
    q_lower = question.lower()
    triggers = ["выручка за", "сумма за", "оборот за", "итого за",
                 "затраты за", "расход за", "доход за", "озп за", "фот за",
                 "какая", "какой", "сколько", "прогноз", "план"]
    if not any(t in q_lower for t in triggers):
        return None

    dates = parse_period(question)
    resource = _resource_name(register_metadata)
    register = _register_name(register_metadata)
    where, params = _build_where(register_metadata, question, dates)

    query = f"""ВЫБРАТЬ ПЕРВЫЕ 1000
    СУММА({resource}) КАК Значение
ИЗ
    {register}{where}"""

    return {"query": query, "params": params}


def _try_group_by(question: str, register_metadata: dict) -> dict | None:
    """Template: group by a dimension."""
    q_lower = question.lower()
    triggers = ["по подразделениям", "по дзо", "по организациям", "по компаниям",
                 "по показателям", "по статьям", "по месяцам", "по сценариям",
                 "в разрезе", "группировка"]
    if not any(t in q_lower for t in triggers):
        return None

    dates = parse_period(question)
    resource = _resource_name(register_metadata)
    register = _register_name(register_metadata)
    dimension = _grouping_dimension(register_metadata, question)
    if not dimension:
        return None

    where, params = _build_where(register_metadata, question, dates)

    query = f"""ВЫБРАТЬ ПЕРВЫЕ 1000
    {dimension},
    СУММА({resource}) КАК Значение
ИЗ
    {register}{where}
СГРУППИРОВАТЬ ПО {dimension}
УПОРЯДОЧИТЬ ПО Значение УБЫВ"""

    return {"query": query, "params": params}


def _try_top_n(question: str, register_metadata: dict) -> dict | None:
    """Template: top N by a dimension."""
    q_lower = question.lower()
    if not any(t in q_lower for t in ["топ", "top", "лучших", "худших"]):
        return None

    m = _TOP_N_RE.search(question)
    n = int(m.group(1)) if m else 10
    order = "ВОЗР" if ("худших" in q_lower or "минимальн" in q_lower) else "УБЫВ"

    dates = parse_period(question)
    resource = _resource_name(register_metadata)
    register = _register_name(register_metadata)
    dimension = _grouping_dimension(register_metadata, question)
    if not dimension:
        return None

    where, params = _build_where(register_metadata, question, dates)

    query = f"""ВЫБРАТЬ ПЕРВЫЕ {n}
    {dimension},
    СУММА({resource}) КАК Значение
ИЗ
    {register}{where}
СГРУППИРОВАТЬ ПО {dimension}
УПОРЯДОЧИТЬ ПО Значение {order}"""

    return {"query": query, "params": params}


def _try_time_series(question: str, register_metadata: dict) -> dict | None:
    """Template: values over time (by month/period)."""
    q_lower = question.lower()
    triggers = ["по месяцам", "помесячно", "динамика", "тренд", "по периодам"]
    if not any(t in q_lower for t in triggers):
        return None

    dates = parse_period(question)
    resource = _resource_name(register_metadata)
    register = _register_name(register_metadata)
    date_field = _date_field(register_metadata)
    dims = {d["name"] for d in register_metadata.get("dimensions", [])}

    # Prefer Месяц if available, else date field
    time_dim = "Месяц" if "Месяц" in dims else date_field
    where, params = _build_where(register_metadata, question, dates)

    query = f"""ВЫБРАТЬ ПЕРВЫЕ 1000
    {time_dim},
    СУММА({resource}) КАК Значение
ИЗ
    {register}{where}
СГРУППИРОВАТЬ ПО {time_dim}
УПОРЯДОЧИТЬ ПО {time_dim}"""

    return {"query": query, "params": params}


def try_match(question: str, register_metadata: dict) -> dict | None:
    """Try to match question against predefined templates.

    Returns: {"query": str, "params": dict} or None.
    """
    for handler in (_try_top_n, _try_time_series, _try_group_by, _try_aggregate):
        result = handler(question, register_metadata)
        if result:
            return result
    return None
