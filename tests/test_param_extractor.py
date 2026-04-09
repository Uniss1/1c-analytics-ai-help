"""Tests for param_extractor — LLM extracts structured JSON."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.param_extractor import extract_params


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
            {"name": "КонтурПоказателя", "data_type": "Строка"},
            {"name": "ДЗО", "data_type": "Строка"},
            {"name": "Сценарий", "data_type": "Строка"},
            {"name": "Месяц", "data_type": "Число"},
        ],
        "resources": [
            {"name": "Сумма", "data_type": "Число"},
            {"name": "Выручка", "data_type": "Число"},
        ],
    }


@pytest.mark.asyncio
async def test_full_extraction(register_meta):
    """LLM returns complete params — no clarification needed."""
    llm_response = json.dumps({
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт", "КонтурПоказателя": "свод"},
        "period": {"from": "2025-03-01", "to": "2025-03-31"},
        "group_by": [],
        "order_by": "desc",
        "limit": 1000,
        "needs_clarification": False,
        "understood": {"описание": "Сумма выручки за март 2025"},
    })

    with patch("api.param_extractor.generate", new_callable=AsyncMock, return_value=llm_response):
        result = await extract_params("выручка за март 2025", register_meta)

    assert not result["needs_clarification"]
    assert result["params"]["resource"] == "Сумма"
    assert result["params"]["period"]["from"] == "2025-03-01"


@pytest.mark.asyncio
async def test_clarification_needed(register_meta):
    """LLM can't determine period — asks for clarification."""
    llm_response = json.dumps({
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт", "КонтурПоказателя": "свод"},
        "period": {"from": None, "to": None},
        "group_by": ["ДЗО"],
        "order_by": "desc",
        "limit": 1000,
        "needs_clarification": True,
        "understood": {"описание": "Выручка по ДЗО, период не указан"},
    })

    with patch("api.param_extractor.generate", new_callable=AsyncMock, return_value=llm_response):
        result = await extract_params("выручка по ДЗО", register_meta)

    assert result["needs_clarification"]
    assert "Правильно я поняла" in result["clarification_text"]
    assert "Период: не указан" in result["clarification_text"]


@pytest.mark.asyncio
async def test_date_fallback(register_meta):
    """LLM misses period but rule-based parser catches it."""
    llm_response = json.dumps({
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт"},
        "period": {"from": None, "to": None},
        "group_by": [],
        "order_by": "desc",
        "limit": 1000,
        "needs_clarification": False,
        "understood": {"описание": "Сумма за Q1 2025"},
    })

    with patch("api.param_extractor.generate", new_callable=AsyncMock, return_value=llm_response):
        result = await extract_params("выручка за 1 квартал 2025", register_meta)

    # date_parser fallback should fill in the period
    assert result["params"]["period"]["from"] == "2025-01-01"
    assert result["params"]["period"]["to"] == "2025-03-31"


@pytest.mark.asyncio
async def test_invalid_json_response(register_meta):
    """LLM returns garbage — graceful fallback."""
    with patch("api.param_extractor.generate", new_callable=AsyncMock, return_value="это не JSON"):
        result = await extract_params("выручка за март", register_meta)

    assert result["needs_clarification"]
    assert "переформулировать" in result["clarification_text"]
    assert result["params"] is None


@pytest.mark.asyncio
async def test_markdown_fenced_json(register_meta):
    """LLM wraps JSON in markdown code fences — still parses."""
    inner = json.dumps({
        "resource": "Сумма",
        "filters": {"Сценарий": "Факт"},
        "period": {"from": "2025-03-01", "to": "2025-03-31"},
        "group_by": [],
        "order_by": "desc",
        "limit": 1000,
        "needs_clarification": False,
        "understood": {"описание": "Сумма за март 2025"},
    })
    llm_response = f"```json\n{inner}\n```"

    with patch("api.param_extractor.generate", new_callable=AsyncMock, return_value=llm_response):
        result = await extract_params("выручка за март 2025", register_meta)

    assert not result["needs_clarification"]
    assert result["params"]["resource"] == "Сумма"
