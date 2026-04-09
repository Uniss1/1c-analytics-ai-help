"""Pre-built query templates for common dashboard questions.

When a question matches a template, LLM is skipped entirely —
only parameter extraction is needed.
"""

import re

from .date_parser import parse_period

# Extract "топ-5", "топ 10", "top-3" from question
_TOP_N_RE = re.compile(r"(?:топ|top)[\s-]*(\d+)", re.IGNORECASE)

TEMPLATES = [
    {
        "name": "sum_for_period",
        "patterns": ["выручка за", "сумма за", "оборот за", "итого за"],
        "template": """ВЫБРАТЬ ПЕРВЫЕ {limit}
    СУММА({resource}) КАК Значение
ИЗ
    РегистрНакопления.{register}.Обороты(&Начало, &Конец,,,)""",
        "params": ["Начало", "Конец"],
    },
    {
        "name": "sum_by_dimension",
        "patterns": ["по подразделениям", "по номенклатуре", "в разрезе"],
        "template": """ВЫБРАТЬ ПЕРВЫЕ {limit}
    {dimension} КАК Группировка,
    СУММА({resource}) КАК Значение
ИЗ
    РегистрНакопления.{register}.Обороты(&Начало, &Конец, ,,,)
СГРУППИРОВАТЬ ПО {dimension}
УПОРЯДОЧИТЬ ПО Значение УБЫВ""",
        "params": ["Начало", "Конец"],
    },
    {
        "name": "top_n",
        "patterns": ["топ", "лучших", "худших", "максимальн", "минимальн"],
        "template": """ВЫБРАТЬ ПЕРВЫЕ {n}
    {dimension} КАК Группировка,
    СУММА({resource}) КАК Значение
ИЗ
    РегистрНакопления.{register}.Обороты(&Начало, &Конец, ,,,)
СГРУППИРОВАТЬ ПО {dimension}
УПОРЯДОЧИТЬ ПО Значение {order}""",
        "params": ["Начало", "Конец"],
    },
]


def try_match(question: str, register_metadata: dict) -> dict | None:
    """Try to match question against predefined templates.

    Returns: {"query": str, "params": dict} or None.
    """
    q_lower = question.lower()

    for tpl in TEMPLATES:
        if not any(p in q_lower for p in tpl["patterns"]):
            continue

        # Extract dates
        dates = parse_period(question) or {}
        params = {}
        for p in tpl["params"]:
            if p in dates:
                params[p] = dates[p]

        # Metadata fields
        register = register_metadata.get("name", "").split(".")[-1]
        resource = register_metadata["resources"][0]["name"] if register_metadata.get("resources") else "Сумма"
        dimension = register_metadata["dimensions"][0]["name"] if register_metadata.get("dimensions") else "Период"

        # Build format values
        fmt = {
            "register": register,
            "resource": resource,
            "dimension": dimension,
            "limit": "1000",
        }

        # Handle top_n
        if tpl["name"] == "top_n":
            m = _TOP_N_RE.search(question)
            fmt["n"] = m.group(1) if m else "10"
            fmt["order"] = "УБЫВ" if "худших" not in q_lower and "минимальн" not in q_lower else "ВОЗР"

        query = tpl["template"].format(**fmt)
        return {"query": query, "params": params}

    return None
