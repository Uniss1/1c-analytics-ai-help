# Single Query Tool — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace 7 tool definitions with a single `query` tool (mode: aggregate/group_by/compare), add template-based answer formatting, remove LLM formatter dependency.

**Architecture:** One Gemma tool call with `mode` enum replaces 7 separate tools. Python normalizes params and formats answers via templates (no LLM). 1C endpoint unchanged.

**Tech Stack:** Python 3.11+, FastAPI, Ollama native `/api/chat`, pytest

**Design doc:** `docs/plans/2026-04-11-single-query-tool-design.md`

---

### Task 1: Create answer_formatter.py (template-based formatting)

**Files:**
- Create: `api/answer_formatter.py`
- Create: `tests/test_answer_formatter.py`

**Step 1: Write the failing tests**

```python
# tests/test_answer_formatter.py
"""Tests for answer_formatter — template-based response formatting."""

import pytest

from api.answer_formatter import format_answer, _fmt_number


class TestFmtNumber:
    def test_billions(self):
        assert _fmt_number(1_500_000_000) == "1,5 млрд"

    def test_millions(self):
        assert _fmt_number(150_000_000) == "150,0 млн"

    def test_millions_fractional(self):
        assert _fmt_number(1_500_000) == "1,5 млн"

    def test_thousands(self):
        assert _fmt_number(50_000) == "50,0 тыс."

    def test_small(self):
        assert _fmt_number(999) == "999"

    def test_negative(self):
        assert _fmt_number(-50_000_000) == "-50,0 млн"

    def test_zero(self):
        assert _fmt_number(0) == "0"


SAMPLE_PARAMS = {
    "resource": "Сумма",
    "filters": {"Показатель": "Выручка", "Сценарий": "Факт", "ДЗО": "Консолидация"},
    "period": {"year": 2025, "month": 3},
    "group_by": [],
    "order_by": "desc",
    "limit": 1000,
}


class TestAggregateFormat:
    def test_basic(self):
        data = [{"Значение": 150_000_000}]
        result = format_answer("aggregate", SAMPLE_PARAMS, data, computed=None)
        assert "Выручка" in result
        assert "Факт" in result or "факт" in result
        assert "март 2025" in result
        assert "150,0 млн" in result
        assert "руб." in result

    def test_with_company(self):
        params = {**SAMPLE_PARAMS, "filters": {**SAMPLE_PARAMS["filters"], "ДЗО": "ДЗО-1"}}
        data = [{"Значение": 80_000_000}]
        result = format_answer("aggregate", params, data, computed=None)
        assert "ДЗО-1" in result
        assert "80,0 млн" in result

    def test_empty_data(self):
        result = format_answer("aggregate", SAMPLE_PARAMS, [], computed=None)
        assert "не найдены" in result.lower()


class TestGroupByFormat:
    def test_basic(self):
        params = {**SAMPLE_PARAMS, "group_by": ["ДЗО"]}
        data = [
            {"ДЗО": "ДЗО-1", "Значение": 150_000_000},
            {"ДЗО": "ДЗО-2", "Значение": 80_000_000},
        ]
        result = format_answer("group_by", params, data, computed=None)
        assert "ДЗО-1" in result
        assert "ДЗО-2" in result
        assert "150,0 млн" in result
        assert "80,0 млн" in result

    def test_empty_data(self):
        params = {**SAMPLE_PARAMS, "group_by": ["ДЗО"]}
        result = format_answer("group_by", params, [], computed=None)
        assert "не найдены" in result.lower()


class TestCompareFormat:
    def test_basic(self):
        params = {
            **SAMPLE_PARAMS,
            "compare_by": "Сценарий",
            "values": ["Факт", "Бюджет"],
        }
        data = [
            {"Сценарий": "Факт", "Значение": 150_000_000},
            {"Сценарий": "Бюджет", "Значение": 200_000_000},
        ]
        computed = {"diff": -50_000_000, "percent": -25.0}
        result = format_answer("compare", params, data, computed=computed)
        assert "Факт" in result
        assert "Бюджет" in result
        assert "150,0 млн" in result
        assert "200,0 млн" in result
        assert "50,0 млн" in result
        assert "25" in result

    def test_empty_data(self):
        params = {**SAMPLE_PARAMS, "compare_by": "Сценарий", "values": ["Факт", "Бюджет"]}
        result = format_answer("compare", params, [], computed=None)
        assert "не найдены" in result.lower()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_answer_formatter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.answer_formatter'`

**Step 3: Write the implementation**

```python
# api/answer_formatter.py
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
        return f"{sign}{abs_val / 1_000_000_000:,.1f} млрд".replace(",", " ").replace(".", ",").replace(" ", ".")
    if abs_val >= 1_000_000:
        return f"{sign}{abs_val / 1_000_000:,.1f} млн".replace(",", " ").replace(".", ",").replace(" ", ".")
    if abs_val >= 1_000:
        return f"{sign}{abs_val / 1_000:,.1f} тыс.".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{sign}{abs_val:,.0f}".replace(",", " ")


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
    metric = filters.get("Показатель", "")
    scenario = filters.get("Сценарий", "")
    company = filters.get("ДЗО", "")
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
```

NOTE: The `_fmt_number` implementation above uses Python's `,` as thousands separator then replaces for Russian locale. The exact formatting needs to produce `"150,0 млн"` style output — implementation may need adjustment during TDD to match test expectations. The tests are the source of truth.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_answer_formatter.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add api/answer_formatter.py tests/test_answer_formatter.py
git commit -m "feat: add template-based answer_formatter (no LLM)"
```

---

### Task 2: Rewrite tool_defs.py — single `query` tool

**Files:**
- Modify: `api/tool_defs.py` (full rewrite)
- Modify: `tests/test_tool_defs.py` (full rewrite)

**Step 1: Write the failing tests**

Replace `tests/test_tool_defs.py`:

```python
# tests/test_tool_defs.py
"""Tests for tool_defs — single query tool schema generation."""

import pytest

from api.tool_defs import build_tools, build_system_message, key_to_dim


@pytest.fixture()
def register_meta():
    return {
        "name": "РегистрСведений.Витрина_Дашборда",
        "description": "Витрина дашборда",
        "dimensions": [
            {
                "name": "Сценарий",
                "data_type": "Строка",
                "required": True,
                "default_value": "Факт",
                "filter_type": "=",
                "allowed_values": ["Факт", "Прогноз", "План"],
                "technical": False,
                "role": "both",
                "description_en": "scenario type (Факт, План, Прогноз)",
            },
            {
                "name": "КонтурПоказателя",
                "data_type": "Строка",
                "required": True,
                "default_value": "свод",
                "filter_type": "=",
                "allowed_values": ["свод", "детализация"],
                "technical": False,
                "role": "filter",
                "description_en": "data contour / aggregation level",
            },
            {
                "name": "Показатель",
                "data_type": "Строка",
                "required": True,
                "default_value": None,
                "filter_type": "=",
                "allowed_values": ["Выручка", "ОЗП", "Маржа", "EBITDA"],
                "technical": False,
                "role": "both",
                "description_en": "metric name (Выручка, Маржа, EBITDA)",
            },
            {
                "name": "ДЗО",
                "data_type": "Строка",
                "required": True,
                "default_value": None,
                "filter_type": "=",
                "allowed_values": ["Консолидация", "ДЗО-1", "ДЗО-2"],
                "technical": False,
                "role": "both",
                "description_en": "company / subsidiary (ДЗО, организация)",
            },
            {
                "name": "Период_Показателя",
                "data_type": "Дата",
                "required": True,
                "default_value": None,
                "filter_type": "year_month",
            },
            {
                "name": "Масштаб",
                "data_type": "Строка",
                "required": False,
                "default_value": None,
                "filter_type": "=",
                "allowed_values": ["тыс.", "млн."],
                "technical": True,
            },
        ],
        "resources": [
            {"name": "Сумма", "data_type": "Число"},
        ],
    }


def test_build_tools_returns_one(register_meta):
    tools = build_tools(register_meta)
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "query"


def test_query_has_mode_enum(register_meta):
    tools = build_tools(register_meta)
    props = tools[0]["function"]["parameters"]["properties"]
    assert "mode" in props
    assert set(props["mode"]["enum"]) == {"aggregate", "group_by", "compare"}


def test_query_has_filter_dims(register_meta):
    tools = build_tools(register_meta)
    props = tools[0]["function"]["parameters"]["properties"]
    assert "scenario" in props
    assert "metric" in props
    assert "company" in props
    assert "contour" in props


def test_technical_excluded(register_meta):
    tools = build_tools(register_meta)
    props = tools[0]["function"]["parameters"]["properties"]
    assert "scale" not in props  # Масштаб is technical


def test_query_has_group_by_with_groupable_only(register_meta):
    tools = build_tools(register_meta)
    props = tools[0]["function"]["parameters"]["properties"]
    assert "group_by" in props
    group_enum = props["group_by"]["enum"]
    assert "contour" not in group_enum  # role=filter
    assert "company" in group_enum     # role=both
    assert "scenario" in group_enum    # role=both


def test_query_has_compare_fields(register_meta):
    tools = build_tools(register_meta)
    props = tools[0]["function"]["parameters"]["properties"]
    assert "compare_values" in props
    assert props["compare_values"]["type"] == "array"
    assert "compare_by" in props


def test_required_minimal(register_meta):
    tools = build_tools(register_meta)
    required = tools[0]["function"]["parameters"]["required"]
    assert "mode" in required
    assert "resource" in required
    assert "year" in required
    assert "month" in required
    # Filters should NOT be required — Python applies defaults
    assert "scenario" not in required
    assert "company" not in required


def test_key_to_dim_roundtrip():
    assert key_to_dim("scenario") == "Сценарий"
    assert key_to_dim("company") == "ДЗО"
    assert key_to_dim("metric") == "Показатель"
    assert key_to_dim("unknown_key") == "unknown_key"


def test_system_message_has_few_shot(register_meta):
    msg = build_system_message(register_meta)
    assert "query(" in msg  # few-shot examples use query() format
    assert "aggregate" in msg
    assert "group_by" in msg
    assert "compare" in msg
    assert "ALWAYS call" in msg
    assert "Витрина_Дашборда" in msg
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tool_defs.py -v`
Expected: FAIL — `test_build_tools_returns_one` fails (currently returns 7)

**Step 3: Rewrite tool_defs.py**

Replace the full content of `api/tool_defs.py`. Key changes:
- `build_tools()` returns a list with 1 tool `query`
- Properties: `mode` (enum 3 values), `resource`, filter dims (from metadata, same `_dim_key` + technical filtering), `year`, `month`, `group_by` (enum from groupable), `compare_by`, `compare_values`
- `required`: only `["mode", "resource", "year", "month"]`
- `build_system_message()` generates prompt with enum listings, mode descriptions, 5 few-shot examples, 5 rules
- Keep `_dim_key()`, `key_to_dim()`, `_KEY_TO_DIM` unchanged — normalization still needs them
- Remove: `_has_required_period()` (year/month always in required), separate tool builder functions

The implementation should:
1. Reuse `_filter_properties()` for filter dimensions (same technical/annotation logic)
2. Reuse `_groupable_dimensions()` for group_by and compare_by enums
3. Generate few-shot examples dynamically using actual enum values from metadata

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tool_defs.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add api/tool_defs.py tests/test_tool_defs.py
git commit -m "feat: single query tool schema with mode enum (replaces 7 tools)"
```

---

### Task 3: Update tool_caller.py — normalize for single tool

**Files:**
- Modify: `api/tool_caller.py:21` — VALID_TOOLS
- Modify: `api/tool_caller.py:220-315` — `_normalize_params()`
- Modify: `tests/test_tool_caller.py` (full rewrite)

**Step 1: Write the failing tests**

Replace `tests/test_tool_caller.py`:

```python
# tests/test_tool_caller.py
"""Tests for tool_caller — normalization of single query tool params."""

from api.tool_caller import _normalize_params


REGISTER_META = {
    "name": "РегистрСведений.Витрина_Дашборда",
    "dimensions": [
        {"name": "Сценарий", "data_type": "Строка", "required": True,
         "default_value": "Факт", "filter_type": "=", "allowed_values": ["Факт", "План"]},
        {"name": "КонтурПоказателя", "data_type": "Строка", "required": True,
         "default_value": "свод", "filter_type": "=", "allowed_values": []},
        {"name": "Показатель", "data_type": "Строка", "required": True,
         "default_value": None, "filter_type": "=", "allowed_values": ["Выручка", "Маржа"]},
        {"name": "ДЗО", "data_type": "Строка", "required": True,
         "default_value": None, "filter_type": "=", "allowed_values": []},
        {"name": "Период_Показателя", "data_type": "Дата", "required": True,
         "default_value": None, "filter_type": "year_month"},
    ],
    "resources": [{"name": "Сумма", "data_type": "Число"}],
}


def test_normalize_aggregate():
    args = {
        "mode": "aggregate",
        "resource": "Сумма",
        "metric": "Выручка",
        "scenario": "Факт",
        "year": 2025,
        "month": 3,
    }
    tool, params = _normalize_params(args, REGISTER_META)
    assert tool == "aggregate"
    assert params["filters"]["Показатель"] == "Выручка"
    assert params["filters"]["Сценарий"] == "Факт"
    assert params["period"] == {"year": 2025, "month": 3}


def test_normalize_aggregate_applies_defaults():
    """Missing scenario → default 'Факт' from metadata."""
    args = {
        "mode": "aggregate",
        "resource": "Сумма",
        "metric": "Выручка",
        "year": 2025,
        "month": 3,
    }
    tool, params = _normalize_params(args, REGISTER_META)
    assert params["filters"]["Сценарий"] == "Факт"
    assert params["filters"]["КонтурПоказателя"] == "свод"


def test_normalize_group_by():
    args = {
        "mode": "group_by",
        "resource": "Сумма",
        "metric": "Выручка",
        "group_by": "company",
        "year": 2025,
        "month": 3,
    }
    tool, params = _normalize_params(args, REGISTER_META)
    assert tool == "group_by"
    assert params["group_by"] == ["ДЗО"]
    # group_by dimension should NOT appear in filters
    assert "ДЗО" not in params["filters"]


def test_normalize_compare():
    args = {
        "mode": "compare",
        "resource": "Сумма",
        "metric": "Выручка",
        "compare_by": "scenario",
        "compare_values": ["Факт", "План"],
        "year": 2025,
        "month": 3,
    }
    tool, params = _normalize_params(args, REGISTER_META)
    assert tool == "compare"
    assert params["compare_by"] == "Сценарий"
    assert params["values"] == ["Факт", "План"]
    # compare_by dimension should NOT appear in filters
    assert "Сценарий" not in params["filters"]


def test_normalize_missing_period_sets_clarification():
    args = {
        "mode": "aggregate",
        "resource": "Сумма",
        "metric": "Выручка",
    }
    tool, params = _normalize_params(args, REGISTER_META)
    assert params["needs_clarification"] is True


def test_normalize_returns_tool_from_mode():
    """Mode becomes the tool name for 1C."""
    args = {"mode": "group_by", "resource": "Сумма", "group_by": "company", "year": 2025, "month": 3}
    tool, params = _normalize_params(args, REGISTER_META)
    assert tool == "group_by"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tool_caller.py -v`
Expected: FAIL — `_normalize_params()` signature changed (now takes `args, metadata` instead of `tool_name, args, metadata`)

**Step 3: Update tool_caller.py**

Changes:
1. `VALID_TOOLS = {"query"}` (line 21)
2. `_normalize_params(args, register_metadata)` — new signature:
   - Extract `mode` from args (this becomes the tool name for 1C)
   - Extract filters from Latin keys → Cyrillic (same logic)
   - Apply defaults (same logic)
   - Handle mode-specific params:
     - `compare`: `compare_by` → Cyrillic, `compare_values` → `values`
     - `group_by`: `group_by` → Cyrillic list
     - `aggregate`: no extra params
   - Return `(tool_name, params)` tuple instead of just `params`
3. `_parse_ollama_response()` — validate tool name is "query" instead of checking against 7 names
4. `call_with_tools()` — return `{"tool": mode, ...}` where mode comes from normalized result (1C sees "aggregate"/"group_by"/"compare", not "query")

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tool_caller.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add api/tool_caller.py tests/test_tool_caller.py
git commit -m "feat: tool_caller normalized for single query tool"
```

---

### Task 4: Update param_validator.py — mode-based validation

**Files:**
- Modify: `api/param_validator.py`
- Modify: `tests/test_param_validator.py`

**Step 1: Write the failing tests**

Replace `tests/test_param_validator.py`:

```python
# tests/test_param_validator.py
"""Tests for param_validator — mode-based validation."""

import pytest

from api.param_validator import validate


@pytest.fixture()
def register_meta():
    return {
        "name": "РегистрСведений.Витрина_Дашборда",
        "resources": [{"name": "Сумма", "data_type": "Число"}],
        "dimensions": [
            {
                "name": "Сценарий",
                "data_type": "Строка",
                "required": True,
                "default_value": "Факт",
                "filter_type": "=",
                "allowed_values": ["Факт", "План", "Прогноз"],
            },
            {
                "name": "Показатель",
                "data_type": "Строка",
                "required": True,
                "default_value": None,
                "filter_type": "=",
                "allowed_values": ["Выручка", "EBITDA", "Маржа"],
            },
        ],
    }


def test_valid_aggregate(register_meta):
    tool_result = {
        "tool": "aggregate",
        "params": {
            "resource": "Сумма",
            "filters": {"Сценарий": "Факт", "Показатель": "Выручка"},
            "period": {"year": 2025, "month": 3},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is True


def test_valid_tools_include_three_modes(register_meta):
    """aggregate, group_by, compare are all valid."""
    for tool in ("aggregate", "group_by", "compare"):
        result = validate(
            {"tool": tool, "params": {"resource": "Сумма", "filters": {}, "period": {"year": 2025, "month": 3}}},
            register_meta,
        )
        # May have other errors but tool name should be valid
        assert not any("инструмент" in e.lower() for e in result.errors)


def test_invalid_tool(register_meta):
    result = validate({"tool": "ratio", "params": {"resource": "Сумма"}}, register_meta)
    assert result.ok is False
    assert any("инструмент" in e.lower() or "tool" in e.lower() for e in result.errors)


def test_invalid_resource(register_meta):
    result = validate(
        {"tool": "aggregate", "params": {"resource": "Несуществующий", "filters": {}, "period": {"year": 2025, "month": 3}}},
        register_meta,
    )
    assert result.ok is False


def test_invalid_filter_value(register_meta):
    result = validate(
        {"tool": "aggregate", "params": {"resource": "Сумма", "filters": {"Сценарий": "XXX"}, "period": {"year": 2025, "month": 3}}},
        register_meta,
    )
    assert result.ok is False
    assert any("Сценарий" in e for e in result.errors)


def test_compare_needs_two_values(register_meta):
    result = validate(
        {"tool": "compare", "params": {"resource": "Сумма", "values": ["Факт"], "filters": {}, "period": {"year": 2025, "month": 3}}},
        register_meta,
    )
    assert result.ok is False


def test_compare_valid(register_meta):
    result = validate(
        {"tool": "compare", "params": {"resource": "Сумма", "compare_by": "Сценарий", "values": ["Факт", "План"], "filters": {}, "period": {"year": 2025, "month": 3}}},
        register_meta,
    )
    assert result.ok is True


def test_group_by_missing(register_meta):
    """group_by mode without group_by param should fail."""
    result = validate(
        {"tool": "group_by", "params": {"resource": "Сумма", "group_by": [], "filters": {}, "period": {"year": 2025, "month": 3}}},
        register_meta,
    )
    assert result.ok is False


def test_no_tool():
    result = validate({"tool": None, "error": "no tool call"}, {})
    assert result.ok is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_param_validator.py -v`
Expected: FAIL — `test_invalid_tool` fails (old VALID_TOOLS still has "ratio")

**Step 3: Update param_validator.py**

Changes:
1. `VALID_TOOLS = {"aggregate", "group_by", "compare"}` (was 7 tools)
2. Add `group_by` mode check: if tool == "group_by" and empty group_by list → error
3. Remove `filtered`-specific checks (condition_operator, condition_value)
4. Remove `ratio`-specific checks
5. Keep: resource, period, filter value checks

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_param_validator.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add api/param_validator.py tests/test_param_validator.py
git commit -m "feat: param_validator for 3 modes (aggregate/group_by/compare)"
```

---

### Task 5: Wire answer_formatter into main.py

**Files:**
- Modify: `api/main.py:23` — replace formatter import
- Modify: `api/main.py:318-330` — replace `format_response()` call

**Step 1: Update imports in main.py**

At line 23, replace:
```python
from .formatter import format_response
```
with:
```python
from .answer_formatter import format_answer
```

**Step 2: Replace formatter call in _handle_data (around line 318-330)**

Replace the formatting block:
```python
    # Format response
    t0 = time.monotonic()
    format_data = data
    if computed:
        format_data = {"rows": data, "computed": computed}
    answer, fmt_debug = await format_response(message, format_data, register_name)
    debug["steps"].append({
        "step": "formatter",
        "raw_data_rows": len(data),
        "raw_llm_response": fmt_debug.get("raw_llm_response"),
        "ms": int((time.monotonic() - t0) * 1000),
    })
```

with:
```python
    # Format response (template, no LLM)
    mode = tool_result.get("tool", "aggregate")
    answer = format_answer(mode, params, data, computed=computed)
    debug["steps"].append({
        "step": "formatter",
        "mode": mode,
        "raw_data_rows": len(data),
    })
```

**Step 3: Same replacement in _handle_clarification_response (around line 418-421)**

Replace:
```python
        answer, _ = await format_response(message, format_data, register_name)
```
with:
```python
        mode = pending.get("tool", "aggregate")
        answer = format_answer(mode, tool_result.get("params", {}), data, computed=computed)
```

**Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS (existing e2e tests may need adjustment if they mock formatter)

**Step 5: Commit**

```bash
git add api/main.py
git commit -m "feat: wire template answer_formatter, remove LLM formatter from data flow"
```

---

### Task 6: Update calibrate_tools.py

**Files:**
- Modify: `scripts/calibrate_tools.py`

**Step 1: Replace TEST_CASES**

All cases now expect tool name `"query"` and include `"mode"` in expected params:

```python
TEST_CASES = [
    # Aggregate — basic
    (
        "Какая выручка за март 2025?",
        "query",
        {"mode": "aggregate", "resource": "Сумма", "metric": "Выручка", "year": 2025, "month": 3},
    ),
    (
        "Сколько EBITDA по факту за январь 2025?",
        "query",
        {"mode": "aggregate", "metric": "EBITDA", "scenario": "Факт", "year": 2025, "month": 1},
    ),
    (
        "Прогноз выручки на декабрь 2025",
        "query",
        {"mode": "aggregate", "scenario": "Прогноз", "metric": "Выручка", "year": 2025, "month": 12},
    ),
    (
        "План по ОЗП на февраль 2025 для ДЗО-1",
        "query",
        {"mode": "aggregate", "scenario": "План", "metric": "ОЗП", "company": "ДЗО-1", "year": 2025, "month": 2},
    ),

    # Group by
    (
        "Выручка по ДЗО за март 2025",
        "query",
        {"mode": "group_by", "group_by": "company", "metric": "Выручка", "year": 2025, "month": 3},
    ),
    (
        "Маржа в разрезе показателей за январь 2025",
        "query",
        {"mode": "group_by", "group_by": "metric", "year": 2025, "month": 1},
    ),
    (
        "Факт по сценариям за март 2025",
        "query",
        {"mode": "group_by", "group_by": "scenario", "year": 2025, "month": 3},
    ),

    # Compare
    (
        "Сравни факт и план по выручке за март 2025",
        "query",
        {"mode": "compare", "compare_by": "scenario", "compare_values": ["Факт", "План"],
         "metric": "Выручка", "year": 2025, "month": 3},
    ),
    (
        "Факт vs бюджет EBITDA за январь 2025",
        "query",
        {"mode": "compare", "compare_by": "scenario", "metric": "EBITDA", "year": 2025, "month": 1},
    ),

    # Edge cases
    (
        "Какая выручка?",
        "query",
        {"mode": "aggregate", "metric": "Выручка"},
    ),
    (
        "Сколько заработали в марте 2025?",
        "query",
        {"mode": "aggregate", "year": 2025, "month": 3},
    ),
    (
        "Маржа по всем ДЗО за февраль 2025",
        "query",
        {"mode": "group_by", "metric": "Маржа", "group_by": "company", "year": 2025, "month": 2},
    ),
]
```

**Step 2: Update check — tool name is always "query"**

The `run_calibration()` function already compares `actual_tool == expected_tool`. Since all cases expect `"query"`, tool selection check is trivially true — the real test is param correctness.

**Step 3: Commit**

```bash
git add scripts/calibrate_tools.py
git commit -m "feat: calibrate_tools for single query tool (12 test cases)"
```

---

### Task 7: Run full test suite and verify

**Step 1: Run all unit tests**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 2: Check for broken imports**

Run: `python -c "from api.main import app; print('OK')"`
Expected: `OK`

**Step 3: If Ollama is available, run calibration**

Run: `python3 scripts/calibrate_tools.py -v`
Expected: 10+/12 pass (mode selection + param filling)

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address test failures from single query tool migration"
```

---

## Execution order and dependencies

```
Task 1 (answer_formatter) ─────────────────────────┐
Task 2 (tool_defs) ──────→ Task 3 (tool_caller) ───┤
                                                     ├──→ Task 5 (main.py) → Task 7 (verify)
Task 4 (param_validator) ──────────────────────────┤
                                                     │
Task 6 (calibrate_tools) ──────────────────────────┘
```

Tasks 1, 2, 4 can run in parallel (no dependencies).
Task 3 depends on Task 2 (imports from tool_defs).
Task 5 depends on Tasks 1, 3, 4 (wires everything together).
Task 6 depends on Tasks 2, 3.
Task 7 is final verification.
