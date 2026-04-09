"""Tests for chat history and cache."""

import pytest
import tempfile
import os

from api.history import (
    init_history,
    create_session,
    save_message,
    get_recent_messages,
    check_cache,
    save_cache,
)


@pytest.fixture(autouse=True)
def _setup_db():
    """Create a temp history.db for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    init_history(path)
    yield
    os.unlink(path)


def test_create_session():
    sid = create_session()
    assert isinstance(sid, str)
    assert len(sid) == 36  # UUID


def test_save_and_get_messages():
    sid = create_session()
    save_message(sid, "user", "Привет")
    save_message(sid, "assistant", "Здравствуйте!", intent="knowledge")

    msgs = get_recent_messages(sid, limit=10)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_get_recent_messages_limit():
    sid = create_session()
    for i in range(10):
        save_message(sid, "user", f"Сообщение {i}")

    msgs = get_recent_messages(sid, limit=3)
    assert len(msgs) == 3
    # Should be the LAST 3 messages
    assert msgs[-1]["content"] == "Сообщение 9"


def test_cache_hit():
    save_cache("выручка за март", "12.4 млн", "data", "sales")
    result = check_cache("выручка за март", "sales")
    assert result is not None
    assert result["answer"] == "12.4 млн"
    assert result["intent"] == "data"


def test_cache_miss():
    result = check_cache("несуществующий вопрос")
    assert result is None


def test_cache_case_insensitive():
    save_cache("Выручка за Март", "12.4 млн", "data")
    result = check_cache("выручка за март")
    assert result is not None


def test_session_history_isolation():
    sid1 = create_session()
    sid2 = create_session()
    save_message(sid1, "user", "Вопрос 1")
    save_message(sid2, "user", "Вопрос 2")

    msgs1 = get_recent_messages(sid1)
    msgs2 = get_recent_messages(sid2)
    assert len(msgs1) == 1
    assert len(msgs2) == 1
    assert msgs1[0]["content"] == "Вопрос 1"
    assert msgs2[0]["content"] == "Вопрос 2"
