"""Tests for query_templates.try_match and date_parser."""

from unittest.mock import patch
from datetime import date

import pytest

from api.query_templates import try_match
from api.date_parser import parse_period


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


# --- try_match tests ---


def test_aggregate_for_period(register_meta):
    result = try_match("выручка за март", register_meta)
    assert result is not None
    assert "СУММА(Сумма)" in result["query"]
    assert "ВитринаВыручка" in result["query"]
    assert "ГДЕ" in result["query"]
    assert "Период_Показателя" in result["query"]
    # Default filters
    assert "Сценарий" in result["query"]
    assert "КонтурПоказателя" in result["query"]
    # No virtual table
    assert "Обороты" not in result["query"]


def test_group_by_dzo(register_meta):
    result = try_match("выручка по ДЗО", register_meta)
    assert result is not None
    assert "СГРУППИРОВАТЬ ПО ДЗО" in result["query"]
    assert "СУММА(Сумма)" in result["query"]


def test_group_by_organizations(register_meta):
    result = try_match("выручка по организациям", register_meta)
    assert result is not None
    assert "СГРУППИРОВАТЬ ПО ДЗО" in result["query"]


def test_top_n(register_meta):
    result = try_match("топ-5 по показателям", register_meta)
    assert result is not None
    assert "ПЕРВЫЕ 5" in result["query"]
    assert "УБЫВ" in result["query"]


def test_time_series(register_meta):
    result = try_match("динамика по месяцам", register_meta)
    assert result is not None
    assert "СГРУППИРОВАТЬ ПО Месяц" in result["query"]
    assert "УПОРЯДОЧИТЬ ПО Месяц" in result["query"]


def test_scenario_default_fact(register_meta):
    result = try_match("выручка за март", register_meta)
    assert result is not None
    assert result["params"].get("Сценарий") == "Факт"
    assert result["params"].get("Контур") == "свод"


def test_scenario_prognoz(register_meta):
    result = try_match("прогноз выручки за март", register_meta)
    assert result is not None
    assert result["params"].get("Сценарий") == "Прогноз"


def test_no_match(register_meta):
    result = try_match("сравни Q1 и Q2", register_meta)
    assert result is None


# --- date_parser tests ---


@patch("api.date_parser.date")
def test_date_parser_month(mock_date):
    mock_date.today.return_value = date(2025, 4, 9)
    mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
    result = parse_period("за март")
    assert result == {"Начало": "2025-03-01", "Конец": "2025-03-31"}


def test_date_parser_quarter():
    result = parse_period("за 1 квартал 2025")
    assert result == {"Начало": "2025-01-01", "Конец": "2025-03-31"}


def test_date_parser_year():
    result = parse_period("за 2024 год")
    assert result == {"Начало": "2024-01-01", "Конец": "2024-12-31"}
