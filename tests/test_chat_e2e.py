"""End-to-end tests for POST /chat (mocked tool_caller + 1C).

Router and wiki/knowledge flow were removed (see
docs/superpowers/plans/2026-04-13-restore-knowledge-endpoint.md), so /chat
always goes straight through the data flow:
    find_register → call_with_tools → param_validator → execute_tool → format_answer
"""

import sqlite3

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from api.history import init_history
from api.metadata import init_metadata


@pytest.fixture(autouse=True)
def _setup_dbs(tmp_path):
    """Init metadata and history DBs for each test."""
    history_path = str(tmp_path / "history.db")
    init_history(history_path)

    meta_path = str(tmp_path / "metadata.db")
    conn = sqlite3.connect(meta_path)
    conn.executescript("""
        CREATE TABLE dashboards (
            id INTEGER PRIMARY KEY, slug TEXT UNIQUE, title TEXT, url_pattern TEXT, updated_at TEXT
        );
        CREATE TABLE registers (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE, description TEXT, register_type TEXT, updated_at TEXT
        );
        CREATE TABLE dashboard_registers (
            dashboard_id INTEGER, register_id INTEGER, widget_title TEXT,
            PRIMARY KEY (dashboard_id, register_id)
        );
        CREATE TABLE dimensions (
            id INTEGER PRIMARY KEY, register_id INTEGER, name TEXT, data_type TEXT, description TEXT,
            required INTEGER NOT NULL DEFAULT 0, default_value TEXT,
            filter_type TEXT NOT NULL DEFAULT '=', allowed_values TEXT,
            technical INTEGER NOT NULL DEFAULT 0, role TEXT, description_en TEXT
        );
        CREATE TABLE resources (
            id INTEGER PRIMARY KEY, register_id INTEGER, name TEXT, data_type TEXT, description TEXT
        );
        CREATE TABLE keywords (
            id INTEGER PRIMARY KEY, register_id INTEGER, keyword TEXT
        );

        INSERT INTO dashboards VALUES (1, 'sales', 'Продажи', '/analytics/sales*', '2025-01-01');
        INSERT INTO registers VALUES (1, 'РегистрНакопления.ВитринаВыручка', 'Выручка', 'accumulation_turnover', '2025-01-01');
        INSERT INTO dashboard_registers VALUES (1, 1, 'Выручка по месяцам');
        INSERT INTO dimensions (id, register_id, name, data_type, required, filter_type, allowed_values)
            VALUES (1, 1, 'Период', 'Дата', 1, 'year_month', NULL);
        INSERT INTO dimensions (id, register_id, name, data_type, required, default_value, filter_type, allowed_values)
            VALUES (2, 1, 'Подразделение', 'Справочник.Подразделения', 0, NULL, '=', NULL);
        INSERT INTO dimensions (id, register_id, name, data_type, required, default_value, filter_type, allowed_values)
            VALUES (3, 1, 'Сценарий', 'Строка', 1, 'Факт', '=', '["Факт", "План"]');
        INSERT INTO resources VALUES (1, 1, 'Сумма', 'Число', NULL);
        INSERT INTO keywords VALUES (1, 1, 'выручка');
        INSERT INTO keywords VALUES (2, 1, 'продажи');
    """)
    conn.commit()
    conn.close()
    init_metadata(meta_path)

    with patch("api.main.METADATA_DB", meta_path), \
         patch("api.main.HISTORY_DB", history_path):
        yield


@pytest.fixture(autouse=True)
def _clear_pending():
    from api.main import _pending_clarifications
    _pending_clarifications.clear()
    yield
    _pending_clarifications.clear()


@pytest.fixture()
def client():
    from api.main import app
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


def _tool_result(*, scenario: str, year: int = 2025, month: int = 3,
                 tool: str = "aggregate", needs_clarification: bool = False) -> dict:
    """Build a tool_caller result with a given scenario filter value."""
    return {
        "tool": tool,
        "args": {"mode": tool, "resource": "Сумма", "scenario": scenario, "year": year, "month": month},
        "params": {
            "resource": "Сумма",
            "filters": {"Сценарий": scenario},
            "period": {"year": year, "month": month},
            "group_by": [],
            "order_by": "desc",
            "limit": 1000,
            "needs_clarification": needs_clarification,
        },
        "raw_response": {},
    }


@pytest.mark.asyncio
async def test_knowledge_endpoint_is_stubbed(client):
    """Knowledge flow is intentionally disabled; endpoint returns 503."""
    async with client:
        resp = await client.post("/knowledge", json={"message": "test"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_clarification_flow_when_period_missing(client):
    """Missing year/month in tool_caller output → user gets a clarification prompt."""
    tool_result = _tool_result(scenario="Факт", needs_clarification=True)
    tool_result["params"]["period"] = {}

    with patch("api.main.call_with_tools", new_callable=AsyncMock,
               return_value=tool_result):
        async with client:
            resp = await client.post("/chat", json={"message": "выручка по ДЗО"})

    body = resp.json()
    assert body["needs_clarification"]
    assert "Уточните" in body["answer"]
    assert body["intent"] == "data"


@pytest.mark.asyncio
@patch("api.main.execute_tool", new_callable=AsyncMock, return_value={
    "success": True, "data": [{"Сумма": 1}], "computed": None,
})
async def test_self_healing_recovers_after_invalid_filter(mock_onec, client):
    """First call uses an invalid scenario, second is corrected via validation feedback."""
    call_with_tools_mock = AsyncMock(side_effect=[
        _tool_result(scenario="Газпром"),  # not in allowed_values → validation fails
        _tool_result(scenario="Факт"),     # corrected on retry
    ])

    with patch("api.main.call_with_tools", call_with_tools_mock):
        async with client:
            resp = await client.post("/chat", json={"message": "выручка за март"})

    body = resp.json()
    assert resp.status_code == 200
    assert not body["needs_clarification"], body
    assert call_with_tools_mock.await_count == 2
    second_call_kwargs = call_with_tools_mock.await_args_list[1].kwargs
    assert "validation_feedback" in second_call_kwargs
    assert "Газпром" in second_call_kwargs["validation_feedback"]


@pytest.mark.asyncio
async def test_self_healing_exhausts_then_asks_clarification(client):
    """After MAX_VALIDATION_RETRIES all-invalid responses, surface clarification."""
    from api.main import MAX_VALIDATION_RETRIES

    call_with_tools_mock = AsyncMock(side_effect=[
        _tool_result(scenario="Газпром") for _ in range(MAX_VALIDATION_RETRIES)
    ])

    with patch("api.main.call_with_tools", call_with_tools_mock):
        async with client:
            resp = await client.post("/chat", json={"message": "выручка за март"})

    body = resp.json()
    assert body["needs_clarification"] is True
    assert call_with_tools_mock.await_count == MAX_VALIDATION_RETRIES
    assert "Некорректные параметры" in body["answer"]


@pytest.mark.asyncio
@patch("api.main.execute_tool", new_callable=AsyncMock, return_value={
    "success": True, "data": [{"Сумма": 1}], "computed": None,
})
async def test_self_healing_skips_retry_on_needs_clarification(mock_onec, client):
    """needs_clarification is a user-data problem, not a validation one — no retry."""
    result = _tool_result(scenario="Факт", needs_clarification=True)
    call_with_tools_mock = AsyncMock(return_value=result)

    with patch("api.main.call_with_tools", call_with_tools_mock):
        async with client:
            resp = await client.post("/chat", json={"message": "выручка"})

    body = resp.json()
    assert body["needs_clarification"] is True
    assert call_with_tools_mock.await_count == 1
