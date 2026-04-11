"""Tests for sync_metadata interview flow."""

import pytest
from unittest.mock import patch
from scripts.sync_metadata import interview_dimension, suggest_description


def test_suggest_description_known_field():
    """Known fields get a predefined suggestion."""
    assert "company" in suggest_description("ДЗО", ["Консолидация", "ДЗО-1"])
    assert "scenario" in suggest_description("Сценарий", ["Факт", "План"])
    assert "metric" in suggest_description("Показатель", ["Выручка", "Маржа"])


def test_suggest_description_unknown_field():
    """Unknown fields get a generated suggestion from values."""
    desc = suggest_description("НовоеПоле", ["Альфа", "Бета"])
    assert "НовоеПоле" in desc


@patch("builtins.input", side_effect=["y"])
def test_interview_technical_field(mock_input):
    """Technical field: only 1 question asked, returns technical=True."""
    dim = {"name": "Масштаб", "data_type": "Строка", "values": ["тыс.", "млн."]}
    result = interview_dimension(dim)
    assert result["technical"] is True
    assert "role" not in result or result.get("role") is None
    assert mock_input.call_count == 1


@patch("builtins.input", side_effect=["n", "b", ""])
def test_interview_user_field_accept_suggestion(mock_input):
    """User field: 3 questions, accept suggested description."""
    dim = {"name": "ДЗО", "data_type": "Строка", "values": ["Консолидация", "ДЗО-1"]}
    result = interview_dimension(dim)
    assert result["technical"] is False
    assert result["role"] == "both"
    assert "company" in result["description_en"]
    assert mock_input.call_count == 3


@patch("builtins.input", side_effect=["n", "f", "custom description here"])
def test_interview_user_field_custom_description(mock_input):
    """User field: operator types custom description."""
    dim = {"name": "ДЗО", "data_type": "Строка", "values": ["Консолидация"]}
    result = interview_dimension(dim)
    assert result["technical"] is False
    assert result["role"] == "filter"
    assert result["description_en"] == "custom description here"
