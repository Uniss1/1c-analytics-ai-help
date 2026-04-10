"""Tests for param_validator — fast JSON validation before 1C call."""

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
    assert result.errors == []


def test_invalid_resource(register_meta):
    tool_result = {
        "tool": "aggregate",
        "params": {
            "resource": "НесуществующийРесурс",
            "filters": {},
            "period": {"year": 2025, "month": 3},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is False
    assert any("resource" in e.lower() or "ресурс" in e.lower() for e in result.errors)


def test_invalid_year(register_meta):
    tool_result = {
        "tool": "aggregate",
        "params": {
            "resource": "Сумма",
            "filters": {},
            "period": {"year": 1900, "month": 3},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is False
    assert any("year" in e.lower() or "год" in e.lower() for e in result.errors)


def test_invalid_month(register_meta):
    tool_result = {
        "tool": "aggregate",
        "params": {
            "resource": "Сумма",
            "filters": {},
            "period": {"year": 2025, "month": 15},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is False
    assert any("month" in e.lower() or "месяц" in e.lower() for e in result.errors)


def test_invalid_filter_value(register_meta):
    tool_result = {
        "tool": "aggregate",
        "params": {
            "resource": "Сумма",
            "filters": {"Сценарий": "НесуществующийСценарий"},
            "period": {"year": 2025, "month": 3},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is False
    assert any("Сценарий" in e for e in result.errors)


def test_compare_needs_two_values(register_meta):
    tool_result = {
        "tool": "compare",
        "params": {
            "resource": "Сумма",
            "compare_by": "Сценарий",
            "values": ["Факт"],  # only 1, need 2
            "filters": {},
            "period": {"year": 2025, "month": 3},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is False
    assert any("2" in e or "values" in e.lower() for e in result.errors)


def test_compare_valid(register_meta):
    tool_result = {
        "tool": "compare",
        "params": {
            "resource": "Сумма",
            "compare_by": "Сценарий",
            "values": ["Факт", "План"],
            "filters": {},
            "period": {"year": 2025, "month": 3},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is True


def test_filtered_invalid_operator(register_meta):
    tool_result = {
        "tool": "filtered",
        "params": {
            "resource": "Сумма",
            "group_by": "Показатель",
            "condition_operator": "LIKE",
            "condition_value": 100,
            "filters": {},
            "period": {"year": 2025, "month": 3},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is False
    assert any("operator" in e.lower() or "оператор" in e.lower() for e in result.errors)


def test_filtered_valid(register_meta):
    tool_result = {
        "tool": "filtered",
        "params": {
            "resource": "Сумма",
            "group_by": "Показатель",
            "condition_operator": ">",
            "condition_value": 100000000,
            "filters": {},
            "period": {"year": 2025, "month": 3},
        },
    }
    result = validate(tool_result, register_meta)
    assert result.ok is True


def test_no_tool_result():
    result = validate({"tool": None, "error": "no tool call"}, {})
    assert result.ok is False
