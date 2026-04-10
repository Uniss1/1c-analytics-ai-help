"""Tests for tool_caller — normalization of new tools (compare, ratio, filtered)."""

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


def test_normalize_compare():
    args = {
        "resource": "Сумма",
        "compare_by": "scenario",
        "values": ["Факт", "План"],
        "year": 2025,
        "month": 3,
    }
    params = _normalize_params("compare", args, REGISTER_META)
    assert params["compare_by"] == "Сценарий"
    assert params["values"] == ["Факт", "План"]
    assert params["period"] == {"year": 2025, "month": 3}


def test_normalize_ratio():
    args = {
        "resource": "Сумма",
        "numerator": "Маржа",
        "denominator": "Выручка",
        "year": 2025,
        "month": 3,
    }
    params = _normalize_params("ratio", args, REGISTER_META)
    assert params["numerator"] == "Маржа"
    assert params["denominator"] == "Выручка"


def test_normalize_filtered():
    args = {
        "resource": "Сумма",
        "group_by": "company",
        "condition_operator": ">",
        "condition_value": 100000000,
        "year": 2025,
        "month": 3,
    }
    params = _normalize_params("filtered", args, REGISTER_META)
    assert params["group_by"] == ["ДЗО"]
    assert params["condition_operator"] == ">"
    assert params["condition_value"] == 100000000


def test_normalize_aggregate_unchanged():
    """Existing aggregate normalization still works."""
    args = {
        "resource": "Сумма",
        "metric": "Выручка",
        "scenario": "Факт",
        "year": 2025,
        "month": 3,
    }
    params = _normalize_params("aggregate", args, REGISTER_META)
    assert params["filters"]["Показатель"] == "Выручка"
    assert params["filters"]["Сценарий"] == "Факт"
    assert params["period"] == {"year": 2025, "month": 3}
