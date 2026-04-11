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
