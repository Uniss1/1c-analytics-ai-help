"""Data-driven calibration case generator.

Reads a register's metadata and synthesises realistic Russian questions
plus their expected canonical tool-call arguments.  The goal is to probe
the tool-calling model with variations the system must survive in prod:

- **base**        — clean Russian, canonical wording
- **declension**  — morphological variants via pymorphy3 ("выручки",
                    "маржу", "по факту", "по ДЗО")
- **typo**        — character-level corruption (swap/drop/duplicate)
- **degraded**    — values outside the register enums, out-of-range
                    periods; the self-healing loop must either recover
                    with valid params or surface a clear error

Expected args always use the register's canonical enum spellings —
regardless of how the question is worded — because that is what the tool
call must contain before hitting 1C.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable

try:
    import pymorphy3
    _MORPH: "pymorphy3.MorphAnalyzer | None" = pymorphy3.MorphAnalyzer()
except ImportError:  # pragma: no cover - calibration-only dep
    _MORPH = None


MONTH_NOM = {
    1: "январь", 2: "февраль", 3: "март", 4: "апрель", 5: "май", 6: "июнь",
    7: "июль", 8: "август", 9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь",
}

# Dimension-name → Latin tool key.  Kept here so the generator does not
# depend on api.tool_defs internals beyond what is re-exported.
from api.tool_defs import _dim_key  # noqa: E402


@dataclass
class CalibrationCase:
    question: str
    expected_mode: str
    expected_args: dict
    category: str                 # base | declension | typo | degraded
    note: str = ""
    degraded_kind: str = ""       # for degraded: invalid_enum | bad_year | bad_month | unknown_value
    # For degraded cases we do not fix expected args — we only check that
    # self-healing either converges to ok=True OR yields needs_clarification.
    expect_recovery: bool = True


# --------------------------------------------------------------------------
# Morphology helpers
# --------------------------------------------------------------------------

def _inflectable(word: str) -> bool:
    """True if pymorphy3 should attempt to inflect this token."""
    if not word:
        return False
    # Skip abbreviations / codes / latin terms — pymorphy will give
    # nonsense results and we would end up with "EBITDAa" or similar.
    if any(c.isdigit() for c in word):
        return False
    if "-" in word or "_" in word:
        return False
    if not any("а" <= c.lower() <= "я" or c.lower() == "ё" for c in word):
        return False
    return True


def inflect_phrase(phrase: str, case: str) -> str:
    """Inflect a Russian phrase token-wise. Only the first inflectable
    token is declined — sufficient for noun phrases like "Выручка от
    реализации" where "от реализации" is a fixed complement."""
    if _MORPH is None or not phrase:
        return phrase
    parts = phrase.split()
    out: list[str] = []
    inflected = False
    for part in parts:
        if not inflected and _inflectable(part):
            try:
                parsed = _MORPH.parse(part)[0]
                infl = parsed.inflect({case})
                if infl:
                    # Preserve leading capitalisation if the original had it
                    w = infl.word
                    if part[0].isupper():
                        w = w[0].upper() + w[1:]
                    out.append(w)
                    inflected = True
                    continue
            except (KeyError, AttributeError, IndexError):
                pass
        out.append(part)
    return " ".join(out)


# --------------------------------------------------------------------------
# Typo generator
# --------------------------------------------------------------------------

def introduce_typo(word: str, rng: random.Random) -> str:
    """Return word with one character-level corruption. Leaves short or
    non-alphabetic words untouched."""
    if len(word) < 5 or not any(c.isalpha() for c in word):
        return word
    # Only corrupt inside a long alphabetic run so we don't break codes
    alpha_positions = [i for i, c in enumerate(word) if c.isalpha()]
    if len(alpha_positions) < 4:
        return word
    i = rng.choice(alpha_positions[1:-1])
    kind = rng.choice(["swap", "drop", "duplicate"])
    chars = list(word)
    if kind == "swap" and i + 1 < len(chars) and chars[i + 1].isalpha():
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    elif kind == "drop":
        del chars[i]
    elif kind == "duplicate":
        chars.insert(i, chars[i])
    return "".join(chars)


# --------------------------------------------------------------------------
# Register introspection
# --------------------------------------------------------------------------

def _find_dim(register: dict, *, key: str | None = None, role: str | None = None) -> dict | None:
    """Find a non-technical, non-period filter dimension.

    Matches by Latin key if provided, else by role preference.
    """
    from api.tool_defs import is_technical_dim

    candidates: list[dict] = []
    for d in register.get("dimensions", []):
        if is_technical_dim(d):
            continue
        if d.get("filter_type") in ("year_month", "range"):
            continue
        if not (d.get("allowed_values") or []):
            continue
        candidates.append(d)

    if key:
        for d in candidates:
            if _dim_key(d["name"]) == key:
                return d
    if role:
        for d in candidates:
            if d.get("role") == role:
                return d
    return candidates[0] if candidates else None


def _resource_name(register: dict) -> str:
    resources = register.get("resources", [])
    return resources[0]["name"] if resources else "Сумма"


# --------------------------------------------------------------------------
# Case generators (one per mode)
# --------------------------------------------------------------------------

def _aggregate_base(register: dict, year: int, month: int) -> list[CalibrationCase]:
    """Clean-wording aggregate questions from register values."""
    resource = _resource_name(register)
    metric_dim = _find_dim(register, key="metric") or _find_dim(register, role="filter")
    scenario_dim = _find_dim(register, key="scenario")
    company_dim = _find_dim(register, key="company")
    month_nom = MONTH_NOM[month]

    cases: list[CalibrationCase] = []
    if metric_dim:
        metric_value = metric_dim["allowed_values"][0]
        cases.append(CalibrationCase(
            question=f"Какая {metric_value} за {month_nom} {year}?",
            expected_mode="aggregate",
            expected_args={
                "mode": "aggregate", "resource": resource,
                _dim_key(metric_dim["name"]): metric_value,
                "year": year, "month": month,
            },
            category="base",
        ))

    if metric_dim and scenario_dim and len(scenario_dim["allowed_values"]) > 0:
        metric_value = metric_dim["allowed_values"][-1]
        scen_value = scenario_dim["allowed_values"][0]
        cases.append(CalibrationCase(
            question=f"Сколько {metric_value} по {scen_value} за {month_nom} {year}?",
            expected_mode="aggregate",
            expected_args={
                "mode": "aggregate", "resource": resource,
                _dim_key(metric_dim["name"]): metric_value,
                _dim_key(scenario_dim["name"]): scen_value,
                "year": year, "month": month,
            },
            category="base",
        ))

    if metric_dim and company_dim:
        metric_value = metric_dim["allowed_values"][0]
        comp_value = company_dim["allowed_values"][-1]
        cases.append(CalibrationCase(
            question=f"{metric_value} по {comp_value} за {month_nom} {year}",
            expected_mode="aggregate",
            expected_args={
                "mode": "aggregate", "resource": resource,
                _dim_key(metric_dim["name"]): metric_value,
                _dim_key(company_dim["name"]): comp_value,
                "year": year, "month": month,
            },
            category="base",
        ))

    return cases


def _group_by_base(register: dict, year: int, month: int) -> list[CalibrationCase]:
    resource = _resource_name(register)
    metric_dim = _find_dim(register, key="metric") or _find_dim(register, role="filter")
    group_dim = _find_dim(register, key="company") or _find_dim(register, role="group_by")
    month_nom = MONTH_NOM[month]

    cases: list[CalibrationCase] = []
    if metric_dim and group_dim and metric_dim is not group_dim:
        metric_value = metric_dim["allowed_values"][0]
        cases.append(CalibrationCase(
            question=f"{metric_value} по {group_dim['name']} за {month_nom} {year}",
            expected_mode="group_by",
            expected_args={
                "mode": "group_by", "resource": resource,
                _dim_key(metric_dim["name"]): metric_value,
                "group_by": _dim_key(group_dim["name"]),
                "year": year, "month": month,
            },
            category="base",
        ))
        cases.append(CalibrationCase(
            question=f"Топ-5 {group_dim['name']} по {metric_value} за {month_nom} {year}",
            expected_mode="group_by",
            expected_args={
                "mode": "group_by", "resource": resource,
                _dim_key(metric_dim["name"]): metric_value,
                "group_by": _dim_key(group_dim["name"]),
                "year": year, "month": month,
            },
            category="base",
        ))
    return cases


def _compare_base(register: dict, year: int, month: int) -> list[CalibrationCase]:
    resource = _resource_name(register)
    metric_dim = _find_dim(register, key="metric") or _find_dim(register, role="filter")
    compare_dim = _find_dim(register, key="scenario") or _find_dim(register, role="group_by")
    month_nom = MONTH_NOM[month]

    cases: list[CalibrationCase] = []
    if compare_dim and len(compare_dim["allowed_values"]) >= 2:
        v1, v2 = compare_dim["allowed_values"][:2]
        args = {
            "mode": "compare", "resource": resource,
            "compare_by": _dim_key(compare_dim["name"]),
            "compare_values": [v1, v2],
            "year": year, "month": month,
        }
        if metric_dim and metric_dim is not compare_dim:
            metric_value = metric_dim["allowed_values"][0]
            args[_dim_key(metric_dim["name"])] = metric_value
            q = f"Сравни {v1} и {v2} по {metric_value} за {month_nom} {year}"
        else:
            q = f"Сравни {v1} и {v2} за {month_nom} {year}"
        cases.append(CalibrationCase(
            question=q,
            expected_mode="compare",
            expected_args=args,
            category="base",
        ))
    return cases


# --------------------------------------------------------------------------
# Variation layer: apply declensions + typos to base cases
# --------------------------------------------------------------------------

_DECLENSIONS = [
    ("gent", "Как было бы '<метрика>' в родительном (кого/чего)"),
    ("datv", "Как '<метрика>' в дательном (кому/чему)"),
    ("accs", "Как '<метрика>' в винительном (кого/что)"),
]


def _declension_variants(case: CalibrationCase, rng: random.Random) -> list[CalibrationCase]:
    """Produce up to 2 declension variants by inflecting enum values inside
    the question.  Expected args stay in canonical form — the model's job
    is to map the declined form back to the enum."""
    if _MORPH is None:
        return []
    variants: list[CalibrationCase] = []
    # Find enum values that appear verbatim in the question and can be inflected
    tokens_to_try = [v for v in case.expected_args.values() if isinstance(v, str)]
    # Also include compare_values list elements
    for v in case.expected_args.get("compare_values", []) or []:
        if isinstance(v, str):
            tokens_to_try.append(v)

    # Pick up to 2 distinct cases
    chosen_cases = rng.sample(_DECLENSIONS, k=min(2, len(_DECLENSIONS)))
    for morph_case, _ in chosen_cases:
        new_q = case.question
        changed = False
        for token in tokens_to_try:
            if token and token in new_q and _inflectable(token.split()[0]):
                declined = inflect_phrase(token, morph_case)
                if declined != token:
                    new_q = new_q.replace(token, declined, 1)
                    changed = True
        if changed and new_q != case.question:
            variants.append(CalibrationCase(
                question=new_q,
                expected_mode=case.expected_mode,
                expected_args=dict(case.expected_args),
                category="declension",
                note=f"case={morph_case}",
            ))
    return variants


def _typo_variants(case: CalibrationCase, rng: random.Random, n: int = 1) -> list[CalibrationCase]:
    """Introduce character-level typos into 1 inflectable token per variant."""
    variants: list[CalibrationCase] = []
    tokens = [t for t in case.question.split() if _inflectable(t) and len(t) >= 5]
    if not tokens:
        return []
    for _ in range(n):
        tok = rng.choice(tokens)
        bad = introduce_typo(tok, rng)
        if bad == tok:
            continue
        new_q = case.question.replace(tok, bad, 1)
        variants.append(CalibrationCase(
            question=new_q,
            expected_mode=case.expected_mode,
            expected_args=dict(case.expected_args),
            category="typo",
            note=f"{tok!r} -> {bad!r}",
        ))
    return variants


# --------------------------------------------------------------------------
# Degraded cases: must trigger self-healing or clarification
# --------------------------------------------------------------------------

_UNKNOWN_COMPANIES = ["Газпром", "Роснефть", "Сбербанк"]
_UNKNOWN_METRICS = ["CAPEX", "OPEX", "NPV"]
_UNKNOWN_SCENARIOS = ["Скорректированный факт", "Оптимистичный прогноз"]


def _degraded(register: dict, year: int, month: int, rng: random.Random) -> list[CalibrationCase]:
    month_nom = MONTH_NOM[month]
    metric_dim = _find_dim(register, key="metric") or _find_dim(register, role="filter")
    company_dim = _find_dim(register, key="company")
    scenario_dim = _find_dim(register, key="scenario")
    cases: list[CalibrationCase] = []

    if metric_dim:
        metric_value = metric_dim["allowed_values"][0]
        # Unknown company
        if company_dim:
            bad = rng.choice(_UNKNOWN_COMPANIES)
            cases.append(CalibrationCase(
                question=f"{metric_value} по {bad} за {month_nom} {year}",
                expected_mode="aggregate",
                expected_args={},
                category="degraded",
                degraded_kind="unknown_value",
                note=f"company '{bad}' absent from enum",
            ))
        # Unknown metric
        bad = rng.choice(_UNKNOWN_METRICS)
        if bad not in metric_dim["allowed_values"]:
            cases.append(CalibrationCase(
                question=f"Какой {bad} за {month_nom} {year}",
                expected_mode="aggregate",
                expected_args={},
                category="degraded",
                degraded_kind="invalid_enum",
                note=f"metric '{bad}' absent from enum",
            ))
        # Unknown scenario
        if scenario_dim:
            bad = rng.choice(_UNKNOWN_SCENARIOS)
            cases.append(CalibrationCase(
                question=f"{metric_value} по сценарию «{bad}» за {month_nom} {year}",
                expected_mode="aggregate",
                expected_args={},
                category="degraded",
                degraded_kind="invalid_enum",
                note=f"scenario '{bad}' absent from enum",
            ))
        # Year out of range
        cases.append(CalibrationCase(
            question=f"{metric_value} за 1999 год",
            expected_mode="aggregate",
            expected_args={},
            category="degraded",
            degraded_kind="bad_year",
            note="year 1999 outside validator range",
        ))
        # Month out of range
        cases.append(CalibrationCase(
            question=f"{metric_value} за месяц 13 {year} года",
            expected_mode="aggregate",
            expected_args={},
            category="degraded",
            degraded_kind="bad_month",
            note="month=13 invalid",
        ))

    return cases


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def generate_cases(
    register: dict,
    *,
    year: int = 2025,
    month: int = 3,
    typo_variants_per_base: int = 1,
    include_declensions: bool = True,
    include_typos: bool = True,
    include_degraded: bool = True,
    seed: int = 42,
) -> list[CalibrationCase]:
    """Generate a calibration test suite from register metadata."""
    rng = random.Random(seed)

    base_cases: list[CalibrationCase] = []
    base_cases += _aggregate_base(register, year, month)
    base_cases += _group_by_base(register, year, month)
    base_cases += _compare_base(register, year, month)

    all_cases: list[CalibrationCase] = list(base_cases)

    if include_declensions:
        for c in base_cases:
            all_cases.extend(_declension_variants(c, rng))

    if include_typos:
        for c in base_cases:
            all_cases.extend(_typo_variants(c, rng, n=typo_variants_per_base))

    if include_degraded:
        all_cases.extend(_degraded(register, year, month, rng))

    return all_cases
