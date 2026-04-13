"""Template-based answer formatting for 1C analytics queries.

No LLM dependency. Formats raw 1C data into human-readable Russian text
based on query mode (aggregate, group_by, compare).
"""

_MONTH_NAMES = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель",
    5: "май", 6: "июнь", 7: "июль", 8: "август",
    9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь",
}


def _fmt_number(value: float) -> str:
    """Format number for human reading: 150000000 → '150,0 млн'."""
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    abs_val = abs(value)
    if abs_val >= 1_000_000_000:
        formatted = f"{abs_val / 1_000_000_000:.1f}"
        return f"{sign}{formatted.replace('.', ',')} млрд"
    if abs_val >= 1_000_000:
        formatted = f"{abs_val / 1_000_000:.1f}"
        return f"{sign}{formatted.replace('.', ',')} млн"
    if abs_val >= 1_000:
        formatted = f"{abs_val / 1_000:.1f}"
        return f"{sign}{formatted.replace('.', ',')} тыс."
    return f"{sign}{abs_val:.0f}"


def _period_str(period: dict) -> str:
    """Format period: {'year': 2025, 'month': 3} → 'март 2025'."""
    month = period.get("month")
    year = period.get("year")
    if month and year:
        return f"{_MONTH_NAMES.get(month, str(month))} {year}"
    if year:
        return str(year)
    return ""


def format_answer(
    mode: str,
    params: dict,
    data: list[dict],
    *,
    computed: dict | None = None,
) -> str:
    """Format 1C query result into a human-readable Russian string."""
    if not data and not computed:
        return "Данные за указанный период не найдены."

    filters = params.get("filters", {})
    period = params.get("period", {})

    def _fval(v):
        """Normalize filter value: list → joined string, scalar → string."""
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return str(v) if v else ""

    metric = _fval(filters.get("Показатель", ""))
    scenario = _fval(filters.get("Сценарий", ""))
    company = _fval(filters.get("ДЗО", ""))
    period_text = _period_str(period)

    if mode == "aggregate":
        return _format_aggregate(metric, scenario, company, period_text, data)
    if mode == "group_by":
        group_dim = (params.get("group_by") or [""])[0]
        return _format_group_by(metric, scenario, company, period_text, group_dim, data)
    if mode == "compare":
        compare_by = params.get("compare_by", "")
        return _format_compare(metric, company, period_text, compare_by, data, computed)

    return "Неизвестный тип запроса."


def _format_aggregate(
    metric: str, scenario: str, company: str, period_text: str, data: list[dict],
) -> str:
    value = data[0].get("Значение", 0) if data else 0
    parts = []
    if metric:
        parts.append(metric)
    context_parts = []
    if company:
        context_parts.append(f"по {company}")
    if scenario:
        context_parts.append(f"по {scenario.lower()}")
    if context_parts:
        parts.append(" ".join(context_parts))
    if period_text:
        parts.append(f"за {period_text}")
    header = " ".join(parts)
    return f"{header} составляет: {_fmt_number(value)} руб."


def _format_group_by(
    metric: str, scenario: str, company: str, period_text: str,
    group_dim: str, data: list[dict],
) -> str:
    parts = []
    if metric:
        parts.append(metric)
    if group_dim:
        parts.append(f"по {group_dim}")
    if period_text:
        parts.append(f"за {period_text}")
    context = []
    if scenario:
        context.append(scenario.lower())
    if company and company != "Консолидация":
        context.append(company)
    if context:
        parts.append(f"({', '.join(context)})")
    header = " ".join(parts)
    lines = [f"{header}:"]
    for row in data:
        dim_value = row.get(group_dim, "")
        value = row.get("Значение", 0)
        lines.append(f"- {dim_value}: {_fmt_number(value)} руб.")
    return "\n".join(lines)


def _format_compare(
    metric: str, company: str, period_text: str,
    compare_by: str, data: list[dict], computed: dict | None,
) -> str:
    parts = []
    if metric:
        parts.append(metric)
    if company and company != "Консолидация":
        parts.append(f"по {company}")
    if period_text:
        parts.append(f"за {period_text}")
    header = " ".join(parts)
    lines = [f"{header}:"]
    for row in data:
        dim_value = row.get(compare_by, "")
        value = row.get("Значение", 0)
        lines.append(f"- {dim_value}: {_fmt_number(value)} руб.")
    if computed:
        diff = computed.get("diff", 0)
        percent = computed.get("percent", 0)
        sign = "+" if diff > 0 else ""
        lines.append(f"- Отклонение: {sign}{_fmt_number(diff)} руб. ({sign}{percent:.1f}%)")
    return "\n".join(lines)
