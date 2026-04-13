"""Tests for scripts/calibration_cases.py — data-driven case generator."""

from collections import Counter

import pytest

from api.tool_defs import _dim_key
from scripts.calibration_cases import (
    CalibrationCase,
    generate_cases,
    inflect_phrase,
    introduce_typo,
)


@pytest.fixture()
def register_meta() -> dict:
    return {
        "name": "РегистрСведений.Витрина_Тест",
        "dimensions": [
            {
                "name": "Сценарий",
                "filter_type": "=",
                "role": "both",
                "required": True,
                "allowed_values": ["Факт", "План", "Прогноз"],
                "default_value": "Факт",
            },
            {
                "name": "Показатель",
                "filter_type": "=",
                "role": "filter",
                "required": True,
                "allowed_values": ["Выручка", "Маржа", "EBITDA"],
            },
            {
                "name": "ДЗО",
                "filter_type": "=",
                "role": "both",
                "required": True,
                "allowed_values": ["Консолидация", "ДЗО-1", "ДЗО-2"],
            },
            {
                "name": "Период_Показателя",
                "filter_type": "year_month",
                "data_type": "Дата",
            },
        ],
        "resources": [{"name": "Сумма"}],
    }


def test_generated_cases_are_not_empty(register_meta):
    cases = generate_cases(register_meta, seed=7)
    assert len(cases) >= 5


def test_generates_every_category(register_meta):
    cases = generate_cases(register_meta, seed=1)
    cats = Counter(c.category for c in cases)
    assert cats["base"] >= 1
    assert cats["declension"] >= 1
    assert cats["typo"] >= 1
    assert cats["degraded"] >= 1


def test_expected_args_use_canonical_enum_values(register_meta):
    """Generated expected args should always match the register's enum spelling,
    even when the question uses declined forms."""
    cases = generate_cases(register_meta, seed=3, include_typos=False, include_degraded=False)
    allowed_metrics = {"Выручка", "Маржа", "EBITDA"}
    for c in cases:
        metric = c.expected_args.get("metric")
        if metric is not None:
            # filter values are now arrays; check each element
            values = metric if isinstance(metric, list) else [metric]
            for v in values:
                assert v in allowed_metrics, (
                    f"non-canonical metric in expected_args: {v!r} for question {c.question!r}"
                )


def test_declension_changes_question_but_not_args(register_meta):
    """A declined variant's expected_args must match SOME base case's expected_args
    — i.e. the canonical enum values are preserved, only the question is declined."""
    cases = generate_cases(
        register_meta, seed=42,
        include_typos=False, include_degraded=False,
    )
    base_args = [c.expected_args for c in cases if c.category == "base"]
    base_questions = {c.question for c in cases if c.category == "base"}
    decls = [c for c in cases if c.category == "declension"]
    assert decls, "no declension cases generated"
    for d in decls:
        assert d.expected_args in base_args, (
            f"declension args not present among bases: {d.expected_args}"
        )
        # The declined question must differ from every base question
        assert d.question not in base_questions


def test_typo_variant_changes_question_only(register_meta):
    cases = generate_cases(
        register_meta, seed=123,
        include_declensions=False, include_degraded=False, typo_variants_per_base=2,
    )
    bases = [c for c in cases if c.category == "base"]
    typos = [c for c in cases if c.category == "typo"]
    base_questions = {b.question for b in bases}
    for t in typos:
        assert t.question not in base_questions
        assert t.expected_mode in {b.expected_mode for b in bases}


def test_degraded_cases_cover_known_failure_kinds(register_meta):
    cases = generate_cases(register_meta, seed=0)
    degraded = [c for c in cases if c.category == "degraded"]
    kinds = {c.degraded_kind for c in degraded}
    # Must include at least the period-range checks + enum violations
    assert "bad_year" in kinds
    assert "bad_month" in kinds
    assert kinds & {"invalid_enum", "unknown_value"}, (
        f"no enum-violation degraded case generated: {kinds}"
    )


def test_inflect_phrase_russian_noun():
    assert inflect_phrase("выручка", "gent") == "выручки"
    assert inflect_phrase("Выручка", "accs") == "Выручку"


def test_inflect_phrase_skips_codes():
    # Codes / abbreviations are returned unchanged
    assert inflect_phrase("ДЗО-1", "gent") == "ДЗО-1"
    assert inflect_phrase("EBITDA", "gent") == "EBITDA"


def test_inflect_phrase_preserves_fixed_tail():
    # Only the head noun is declined; complement stays untouched
    result = inflect_phrase("Выручка от реализации", "gent")
    assert "от реализации" in result
    assert "Выручки" in result or "выручки" in result


def test_typo_leaves_short_words_alone():
    import random
    rng = random.Random(0)
    assert introduce_typo("XY", rng) == "XY"
    assert introduce_typo("ДЗО", rng) == "ДЗО"


def test_typo_changes_long_word():
    import random
    rng = random.Random(1)
    original = "Консолидация"
    typo = introduce_typo(original, rng)
    assert typo != original
    assert len(typo) in {len(original) - 1, len(original), len(original) + 1}


def test_generator_is_deterministic_with_seed(register_meta):
    a = generate_cases(register_meta, seed=100)
    b = generate_cases(register_meta, seed=100)
    assert [c.question for c in a] == [c.question for c in b]


def test_different_register_produces_different_values():
    reg_a = {
        "name": "A",
        "dimensions": [
            {"name": "Показатель", "filter_type": "=", "role": "filter",
             "required": True, "allowed_values": ["Выручка"]},
            {"name": "ДЗО", "filter_type": "=", "role": "both",
             "required": True, "allowed_values": ["ДЗО-1"]},
        ],
        "resources": [{"name": "Сумма"}],
    }
    reg_b = {
        "name": "B",
        "dimensions": [
            {"name": "Показатель", "filter_type": "=", "role": "filter",
             "required": True, "allowed_values": ["Выручка от реализации"]},
            {"name": "ДЗО", "filter_type": "=", "role": "both",
             "required": True, "allowed_values": ["Альфа"]},
        ],
        "resources": [{"name": "Сумма_нетто"}],
    }
    cases_a = generate_cases(reg_a, seed=1, include_typos=False, include_degraded=False)
    cases_b = generate_cases(reg_b, seed=1, include_typos=False, include_degraded=False)
    text_a = " ".join(c.question for c in cases_a)
    text_b = " ".join(c.question for c in cases_b)
    assert "Выручка от реализации" in text_b
    assert "Альфа" in text_b
    assert "Выручка от реализации" not in text_a
    assert "Альфа" not in text_a


def test_filter_values_are_lists(register_meta):
    """All filter-dimension values in expected_args must be lists (new contract)."""
    cases = generate_cases(
        register_meta, seed=5,
        include_declensions=False, include_typos=False, include_degraded=False,
    )
    # Keys that are NOT filter values and should stay scalar
    non_filter_keys = {"mode", "resource", "year", "month", "group_by", "compare_by", "compare_values"}
    for c in cases:
        for key, val in c.expected_args.items():
            if key not in non_filter_keys:
                assert isinstance(val, list), (
                    f"expected_args[{key!r}] should be a list, got {type(val).__name__!r} "
                    f"({val!r}) in case: {c.question!r}"
                )


def test_year_only_case_has_no_month(register_meta):
    cases = generate_cases(
        register_meta, year=2025, month=3,
        include_declensions=False, include_typos=False, include_degraded=False,
    )
    year_only = [c for c in cases if c.note == "year-only period"]
    assert len(year_only) >= 1, "Expected at least one year-only case"
    case = year_only[0]
    assert "month" not in case.expected_args
    assert case.expected_args.get("year") == 2025


def test_multi_value_company_case(register_meta):
    cases = generate_cases(
        register_meta, year=2025, month=3,
        include_declensions=False, include_typos=False, include_degraded=False,
    )
    multi = [c for c in cases if c.note == "multi-value company + year-only"]
    # Only present when register has ≥2 companies and a metric dim.
    if multi:
        case = multi[0]
        # company key should be a list of 2 values
        company_key = _dim_key("ДЗО")
        assert isinstance(case.expected_args.get(company_key), list)
        assert len(case.expected_args[company_key]) == 2
        assert "month" not in case.expected_args
