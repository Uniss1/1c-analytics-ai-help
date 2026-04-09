"""Validate and sanitize generated 1C queries."""

import re

ALLOWED_KEYWORDS = {
    "ВЫБРАТЬ", "ИЗ", "ГДЕ", "СГРУППИРОВАТЬ", "УПОРЯДОЧИТЬ",
    "ПЕРВЫЕ", "МЕЖДУ", "И", "ИЛИ", "НЕ", "КАК", "ИМЕЮЩИЕ",
    "СОЕДИНЕНИЕ", "ЛЕВОЕ", "ПРАВОЕ", "ПОЛНОЕ", "ВНУТРЕННЕЕ",
    "КОЛИЧЕСТВО", "СУММА", "МАКСИМУМ", "МИНИМУМ", "СРЕДНЕЕ",
    "РАЗЛИЧНЫЕ", "ВСЕ", "ОБЪЕДИНИТЬ",
}

FORBIDDEN_PATTERN = re.compile(
    r"\b(ПОМЕСТИТЬ|УНИЧТОЖИТЬ|УДАЛИТЬ|ИЗМЕНИТЬ|СОЗДАТЬ|ОБНОВИТЬ|ПЕРЕСЕКЕМ)\b",
    re.IGNORECASE,
)

REGISTER_PATTERN = re.compile(
    r"РегистрНакопления\.(\w+?)(?:\.|$)",
)

# Catch hallucinated references to catalogs, documents, etc.
OBJECT_PATTERN = re.compile(
    r"(Справочник|Документ|ПланСчетов|ПланВидовХарактеристик)\.\w+",
)


def validate_params(params: dict, register_metadata: dict) -> tuple[bool, list[str]]:
    """Validate that param values are in allowed lists.

    Returns (is_valid, list of error messages).
    """
    errors = []
    filters = params.get("filters", {})
    dims_by_name = {d["name"]: d for d in register_metadata.get("dimensions", [])}

    for dim_name, value in filters.items():
        if value is None:
            continue
        dim = dims_by_name.get(dim_name)
        if not dim:
            continue
        allowed = dim.get("allowed_values") or []
        if allowed and value not in allowed:
            errors.append(f"{dim_name}: '{value}' не из допустимых {allowed}")

    return len(errors) == 0, errors


def validate_query(
    query: str, allowed_registers: set[str]
) -> tuple[bool, str, str]:
    """Validate query against whitelist and safety rules.

    Returns: (is_valid, error_message, sanitized_query)
    """
    stripped = query.strip()

    # No forbidden keywords (checked before ВЫБРАТЬ to give specific error)
    match = FORBIDDEN_PATTERN.search(stripped)
    if match:
        return False, f"Запрещено: {match.group()}", ""

    # Must start with ВЫБРАТЬ
    if not stripped.upper().startswith("ВЫБРАТЬ"):
        return False, "Запрос должен начинаться с ВЫБРАТЬ", ""

    # Check register whitelist
    found_registers = REGISTER_PATTERN.findall(stripped)
    for reg_name in found_registers:
        full_name = f"РегистрНакопления.{reg_name}"
        if full_name not in allowed_registers:
            return False, f"Регистр не из разрешенного списка: {full_name}", ""

    # Block hallucinated object references (catalogs, documents, etc.)
    found_objects = OBJECT_PATTERN.findall(stripped)
    if found_objects:
        return False, f"Запрещены ссылки на объекты: {', '.join(found_objects)}", ""

    # Enforce row limit
    sanitized = stripped
    if "ПЕРВЫЕ" not in sanitized.upper():
        sanitized = sanitized.replace("ВЫБРАТЬ", "ВЫБРАТЬ ПЕРВЫЕ 1000", 1)

    return True, "", sanitized
