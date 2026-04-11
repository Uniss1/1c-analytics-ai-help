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
