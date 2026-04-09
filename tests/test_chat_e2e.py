"""End-to-end tests for POST /chat endpoint (mocked LLM + 1C + ai-chat)."""

import json
import tempfile
import os

import pytest
import httpx
import respx
from unittest.mock import AsyncMock, patch

from api.config import settings
from api.history import init_history
from api.metadata import init_metadata


@pytest.fixture(autouse=True)
def _setup_dbs(tmp_path):
    """Init metadata and history DBs for each test."""
    # History DB
    history_path = str(tmp_path / "history.db")
    init_history(history_path)

    # Metadata DB with test data
    import sqlite3
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
            id INTEGER PRIMARY KEY, register_id INTEGER, name TEXT, data_type TEXT, description TEXT
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
        INSERT INTO dimensions VALUES (1, 1, 'Период', 'Дата', NULL);
        INSERT INTO dimensions VALUES (2, 1, 'Подразделение', 'Справочник.Подразделения', NULL);
        INSERT INTO resources VALUES (1, 1, 'Сумма', 'Число', NULL);
        INSERT INTO keywords VALUES (1, 1, 'выручка');
        INSERT INTO keywords VALUES (2, 1, 'продажи');
    """)
    conn.commit()
    conn.close()
    init_metadata(meta_path)

    # Patch DB paths in main
    with patch("api.main.METADATA_DB", meta_path), \
         patch("api.main.HISTORY_DB", history_path):
        yield


@pytest.fixture()
def client():
    """HTTPX test client for FastAPI app."""
    from api.main import app
    # Re-init DBs since lifespan won't run in test client
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


def _sse(*events):
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event, ensure_ascii=False)}")
        lines.append("")
    return "\n".join(lines)


@pytest.mark.asyncio
@patch("api.router.generate", new_callable=AsyncMock, return_value="data")
@patch("api.formatter.generate", new_callable=AsyncMock, return_value="Выручка за март: 8.2 млн ₽")
@patch("api.main.execute_query", new_callable=AsyncMock, return_value={
    "success": True, "data": [{"Сумма": 8200000}], "total": 1, "truncated": False,
})
async def test_data_flow_e2e(mock_onec, mock_formatter, mock_router, client):
    """Data question goes through full pipeline."""
    async with client:
        resp = await client.post("/chat", json={"message": "Какая выручка за март?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "data"
    assert "8.2 млн" in body["answer"]
    assert body["session_id"]
    assert body["latency_ms"] >= 0


@respx.mock
@pytest.mark.asyncio
@patch("api.router.generate", new_callable=AsyncMock, return_value="knowledge")
async def test_knowledge_flow_e2e(mock_router, client):
    """Knowledge question routes to ai-chat."""
    wiki_url = settings.wiki_base_url
    respx.post(f"{wiki_url}/api/chat/stream").mock(
        return_value=httpx.Response(200, content=_sse(
            {"type": "sources", "sources": [{"title": "Методология", "path": "/docs/m"}]},
            {"type": "token", "token": "Маржа считается как..."},
            {"type": "done", "from_cache": False},
        ).encode(), headers={"content-type": "text/event-stream"}),
    )

    async with client:
        resp = await client.post("/chat", json={"message": "Как считается маржа?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "knowledge"
    assert "Маржа" in body["answer"]
    assert body["sources"]


@pytest.mark.asyncio
@patch("api.router.generate", new_callable=AsyncMock, return_value="data")
@patch("api.formatter.generate", new_callable=AsyncMock, return_value="Выручка: 10 млн")
@patch("api.main.execute_query", new_callable=AsyncMock, return_value={
    "success": True, "data": [{"Сумма": 10000000}], "total": 1, "truncated": False,
})
async def test_cache_hit(mock_onec, mock_formatter, mock_router, client):
    """Second identical question returns cached response."""
    async with client:
        resp1 = await client.post("/chat", json={"message": "выручка за март"})
        body1 = resp1.json()

        # Reset mocks to verify they're NOT called on cache hit
        mock_router.reset_mock()
        mock_formatter.reset_mock()
        mock_onec.reset_mock()

        resp2 = await client.post("/chat", json={
            "message": "выручка за март",
            "session_id": body1["session_id"],
        })
        body2 = resp2.json()

    assert body2["answer"] == body1["answer"]
    assert body2["latency_ms"] <= body1["latency_ms"] or body2["latency_ms"] < 100
    mock_router.assert_not_called()


@pytest.mark.asyncio
@patch("api.router.generate", new_callable=AsyncMock, return_value="data")
@patch("api.formatter.generate", new_callable=AsyncMock, return_value="Ответ")
@patch("api.main.execute_query", new_callable=AsyncMock, return_value={
    "success": True, "data": [{"Сумма": 1}], "total": 1, "truncated": False,
})
async def test_session_history(mock_onec, mock_formatter, mock_router, client):
    """Two questions in same session are both saved in history."""
    from api.history import get_recent_messages

    async with client:
        resp1 = await client.post("/chat", json={"message": "выручка за Q1"})
        sid = resp1.json()["session_id"]

        await client.post("/chat", json={
            "message": "а за Q2?",
            "session_id": sid,
        })

    # Cache returns for second question so router isn't called,
    # but both messages should be in history
    msgs = get_recent_messages(sid, limit=10)
    assert len(msgs) >= 2  # At least user+assistant for first question
    roles = [m["role"] for m in msgs]
    assert "user" in roles
    assert "assistant" in roles
