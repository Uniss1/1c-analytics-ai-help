"""Tests for onec_client — execute_tool sends JSON to 1C."""

import pytest
import httpx

from api.onec_client import execute_tool


@pytest.fixture()
def mock_1c_success(monkeypatch):
    """Mock httpx to return a successful 1C response."""
    async def mock_post(self, url, **kwargs):
        assert "/analytics/execute" in url
        body = kwargs.get("json", {})
        assert "register" in body
        assert "tool" in body
        assert "params" in body
        resp = httpx.Response(
            200,
            json={
                "success": True,
                "data": [{"Сценарий": "Факт", "Значение": 150}],
                "computed": None,
            },
            request=httpx.Request("POST", url),
        )
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)


@pytest.fixture()
def mock_1c_error(monkeypatch):
    """Mock httpx to return a 1C validation error."""
    async def mock_post(self, url, **kwargs):
        resp = httpx.Response(
            200,
            json={
                "success": False,
                "error_type": "invalid_params",
                "error_message": "Неизвестное значение",
                "allowed_values": ["Факт", "План"],
            },
            request=httpx.Request("POST", url),
        )
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)


@pytest.mark.asyncio
async def test_execute_tool_success(mock_1c_success):
    tool_result = {
        "tool": "aggregate",
        "params": {
            "resource": "Сумма",
            "filters": {"Сценарий": "Факт"},
            "period": {"year": 2025, "month": 3},
        },
    }
    result = await execute_tool(
        tool_result,
        register_name="РегистрСведений.Витрина_Дашборда",
    )
    assert result["success"] is True
    assert len(result["data"]) == 1


@pytest.mark.asyncio
async def test_execute_tool_error(mock_1c_error):
    tool_result = {
        "tool": "aggregate",
        "params": {"resource": "Сумма", "filters": {}, "period": {}},
    }
    result = await execute_tool(
        tool_result,
        register_name="РегистрСведений.Витрина_Дашборда",
    )
    assert result["success"] is False
    assert result["error_type"] == "invalid_params"
