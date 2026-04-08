"""Tests for 1C query validation."""

import pytest

from api.query_validator import validate_query


@pytest.fixture()
def whitelist():
    return {"РегистрНакопления.ВитринаВыручка", "РегистрНакопления.ВитринаЗатрат"}


def test_valid_select(whitelist):
    query = "ВЫБРАТЬ ПЕРВЫЕ 100 Сумма ИЗ РегистрНакопления.ВитринаВыручка.Обороты(,,,)"
    is_valid, error, sanitized = validate_query(query, whitelist)
    assert is_valid is True
    assert error == ""
    assert "ПЕРВЫЕ 100" in sanitized


def test_reject_delete(whitelist):
    query = "УДАЛИТЬ ИЗ РегистрНакопления.ВитринаВыручка"
    is_valid, error, sanitized = validate_query(query, whitelist)
    assert is_valid is False
    assert "forbidden" in error.lower() or "запрещен" in error.lower()


def test_reject_unknown_register(whitelist):
    query = "ВЫБРАТЬ * ИЗ РегистрНакопления.СекретныйРегистр.Обороты(,,,)"
    is_valid, error, sanitized = validate_query(query, whitelist)
    assert is_valid is False
    assert "whitelist" in error.lower() or "разрешен" in error.lower()


def test_add_limit(whitelist):
    query = "ВЫБРАТЬ Сумма ИЗ РегистрНакопления.ВитринаВыручка.Обороты(,,,)"
    is_valid, error, sanitized = validate_query(query, whitelist)
    assert is_valid is True
    assert "ПЕРВЫЕ 1000" in sanitized


def test_keep_existing_limit(whitelist):
    query = "ВЫБРАТЬ ПЕРВЫЕ 50 Сумма ИЗ РегистрНакопления.ВитринаВыручка.Обороты(,,,)"
    is_valid, error, sanitized = validate_query(query, whitelist)
    assert is_valid is True
    assert "ПЕРВЫЕ 50" in sanitized
    assert "ПЕРВЫЕ 1000" not in sanitized
