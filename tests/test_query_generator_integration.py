"""Integration tests for query_generator — template path and LLM path."""

from unittest.mock import AsyncMock, patch

import pytest

from api.query_generator import generate_query


@pytest.fixture()
def register_meta():
    return {
        "name": "РегистрНакопления.ВитринаВыручка",
        "description": "Выручка по подразделениям и номенклатуре",
        "register_type": "accumulation_turnover",
        "dimensions": [
            {"name": "Подразделение", "data_type": "Справочник.Подразделения"},
        ],
        "resources": [
            {"name": "Сумма", "data_type": "Число"},
        ],
    }


@pytest.mark.asyncio
async def test_template_path(register_meta):
    """Template match — LLM should NOT be called."""
    with patch("api.query_generator.generate") as mock_llm:
        result = await generate_query("выручка за март", register_meta)

    mock_llm.assert_not_called()
    assert "СУММА(Сумма)" in result["query"]
    assert "ВитринаВыручка.Обороты" in result["query"]


@pytest.mark.asyncio
async def test_llm_path(register_meta):
    """No template match — falls back to LLM, validates result."""
    llm_response = (
        "ВЫБРАТЬ ПЕРВЫЕ 1000\n"
        "    Сумма КАК Q1,\n"
        "    Сумма КАК Q2\n"
        "ИЗ\n"
        "    РегистрНакопления.ВитринаВыручка.Обороты(&Начало, &Конец,,,)"
    )
    with patch(
        "api.query_generator.generate",
        new_callable=AsyncMock,
        return_value=llm_response,
    ) as mock_llm:
        result = await generate_query("сравни Q1 и Q2 2025", register_meta)

    mock_llm.assert_called_once()
    assert "ВЫБРАТЬ" in result["query"]
    assert "ВитринаВыручка" in result["query"]


@pytest.mark.asyncio
async def test_llm_invalid_query_raises(register_meta):
    """LLM returns invalid query — should raise ValueError."""
    with patch(
        "api.query_generator.generate",
        new_callable=AsyncMock,
        return_value="УДАЛИТЬ ВСЕ ИЗ Таблица",
    ):
        with pytest.raises(ValueError, match="невалидный запрос"):
            await generate_query("удали всё", register_meta)
