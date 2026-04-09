"""Tests for query_builder — deterministic JSON params → 1C query."""

import pytest

from api.query_builder import build_query


@pytest.fixture()
def register_meta():
    """Register metadata matching real 1C structure."""
    return {
        "name": "РегистрНакопления.ВитринаВыручка",
        "description": "ВитринаВыручка",
        "register_type": "accumulation_turnover",
        "dimensions": [
            {"name": "Период_Показателя", "data_type": "Дата"},
            {"name": "Показатель", "data_type": "Строка"},
            {"name": "Показатель_номер", "data_type": "Строка"},
            {"name": "КонтурПоказателя", "data_type": "Строка"},
            {"name": "ПризнакДоход", "data_type": "Строка"},
            {"name": "ДЗО", "data_type": "Строка"},
            {"name": "Сценарий", "data_type": "Строка"},
            {"name": "Масштаб", "data_type": "Строка"},
            {"name": "Ед_изм", "data_type": "Строка"},
            {"name": "Месяц", "data_type": "Число"},
        ],
        "resources": [
            {"name": "Сумма", "data_type": "Число"},
            {"name": "Выручка", "data_type": "Число"},
            {"name": "ОЗП", "data_type": "Число"},
        ],
    }


def test_simple_aggregate(register_meta):
    """Simple SUM query with period and default filters."""
    params = {
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт", "КонтурПоказателя": "свод"},
        "period": {"from": "2025-03-01", "to": "2025-03-31"},
        "group_by": [],
        "order_by": "desc",
        "limit": 1000,
    }
    result = build_query(params, register_meta)

    assert "СУММА(Сумма)" in result["query"]
    assert "ВитринаВыручка" in result["query"]
    assert "Период_Показателя >= &Начало" in result["query"]
    assert "Период_Показателя <= &Конец" in result["query"]
    assert "Сценарий = &Сценарий" in result["query"]
    assert result["params"]["Начало"] == "2025-03-01"
    assert result["params"]["Конец"] == "2025-03-31"
    assert result["params"]["Сценарий"] == "Факт"
    assert result["params"]["КонтурПоказателя"] == "свод"


def test_group_by_dzo(register_meta):
    """Group by ДЗО dimension."""
    params = {
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт", "КонтурПоказателя": "свод"},
        "period": {"from": "2025-01-01", "to": "2025-03-31"},
        "group_by": ["ДЗО"],
        "order_by": "desc",
        "limit": 1000,
    }
    result = build_query(params, register_meta)

    assert "ДЗО," in result["query"]
    assert "СГРУППИРОВАТЬ ПО ДЗО" in result["query"]
    assert "УПОРЯДОЧИТЬ ПО Значение УБЫВ" in result["query"]


def test_top_n(register_meta):
    """Top-5 query with limit."""
    params = {
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт", "КонтурПоказателя": "свод"},
        "period": {"from": None, "to": None},
        "group_by": ["Показатель"],
        "order_by": "desc",
        "limit": 5,
    }
    result = build_query(params, register_meta)

    assert "ПЕРВЫЕ 5" in result["query"]
    assert "Показатель," in result["query"]
    assert "СГРУППИРОВАТЬ ПО Показатель" in result["query"]
    # No period in WHERE
    assert "Начало" not in result["params"]


def test_ascending_order(register_meta):
    """Ascending order (worst performers)."""
    params = {
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт"},
        "period": {"from": "2025-01-01", "to": "2025-12-31"},
        "group_by": ["ДЗО"],
        "order_by": "asc",
        "limit": 5,
    }
    result = build_query(params, register_meta)

    assert "ВОЗР" in result["query"]


def test_no_filters(register_meta):
    """Query without any filters."""
    params = {
        "resource": "Сумма",
        "filters": {},
        "period": {"from": None, "to": None},
        "group_by": [],
        "order_by": "desc",
        "limit": 1000,
    }
    result = build_query(params, register_meta)

    assert "ГДЕ" not in result["query"]
    assert result["params"] == {}


def test_null_filter_values_ignored(register_meta):
    """Null filter values are not included in WHERE."""
    params = {
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт", "ДЗО": None, "КонтурПоказателя": None},
        "period": {"from": None, "to": None},
        "group_by": [],
        "order_by": "desc",
        "limit": 1000,
    }
    result = build_query(params, register_meta)

    assert "Сценарий = &Сценарий" in result["query"]
    assert "ДЗО" not in result["query"]
    assert "КонтурПоказателя" not in result["query"]


def test_prognoz_scenario(register_meta):
    """Scenario Прогноз instead of Факт."""
    params = {
        "resource": "Сумма",
        "filters": {"Сценарий": "Прогноз", "КонтурПоказателя": "свод"},
        "period": {"from": "2025-03-01", "to": "2025-03-31"},
        "group_by": [],
        "order_by": "desc",
        "limit": 1000,
    }
    result = build_query(params, register_meta)

    assert result["params"]["Сценарий"] == "Прогноз"
