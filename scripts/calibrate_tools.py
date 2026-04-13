#!/usr/bin/env python3
"""Data-driven calibration for the tool-calling pipeline.

Loads the target register from metadata.db, generates realistic Russian
questions (with morphological declensions and typos via pymorphy3), and
exercises the full self-healing loop — no hardcoded enum values.

Configuration defaults come from .env (api/config.py). CLI flags override.

Usage:
    python3 scripts/calibrate_tools.py
    python3 scripts/calibrate_tools.py --url http://10.10.90.188:11443 -v
    python3 scripts/calibrate_tools.py --no-typos --year 2024 --month 6
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.config import settings
from api.metadata import init_metadata, get_all_registers
from api.param_validator import validate as validate_tool_params
from api.tool_caller import call_with_tools
from api.tool_defs import build_tools
from scripts.calibration_cases import CalibrationCase, generate_cases

DB_PATH = str(Path(__file__).parent.parent / "metadata.db")
MAX_VALIDATION_RETRIES = 3


def load_register(register_name: str | None) -> dict:
    init_metadata(DB_PATH)
    registers = get_all_registers()
    if not registers:
        print("ERROR: metadata.db is empty. Run: python3 scripts/seed_metadata.py")
        sys.exit(1)
    if register_name:
        for reg in registers:
            if reg["name"] == register_name:
                return reg
        names = [r["name"] for r in registers]
        print(f"ERROR: register {register_name!r} not found. Available: {names}")
        sys.exit(1)
    return registers[0]


def check_params(expected: dict, actual: dict) -> list[str]:
    errors: list[str] = []
    for key, exp_val in expected.items():
        act_val = actual.get(key)
        if act_val is None:
            errors.append(f"  missing: {key} (expected {exp_val!r})")
        elif isinstance(exp_val, list):
            if not isinstance(act_val, list):
                errors.append(f"  {key}: expected list, got {type(act_val).__name__}")
            elif sorted(str(x) for x in exp_val) != sorted(str(x) for x in act_val):
                errors.append(f"  {key}: expected {exp_val!r}, got {act_val!r}")
        elif act_val != exp_val:
            errors.append(f"  {key}: expected {exp_val!r}, got {act_val!r}")
    # Flag explicit regressions: if `month` is expected to be absent
    # (year-only queries), emitting it is a mistake.
    if "month" not in expected and "month" in actual and actual.get("month") is not None:
        errors.append(f"  month: expected absent (year-only query), got {actual['month']!r}")
    return errors


async def _call_with_self_healing(
    question: str, register: dict, *,
    model: str, base_url: str, api_key: str,
) -> tuple[dict, int, list[list[str]]]:
    feedback: str | None = None
    errors_per_attempt: list[list[str]] = []
    result: dict = {}
    for attempt in range(1, MAX_VALIDATION_RETRIES + 1):
        result = await call_with_tools(
            question, register,
            model=model, base_url=base_url, api_key=api_key,
            validation_feedback=feedback,
        )
        if not result.get("tool"):
            errors_per_attempt.append(["no tool call"])
            return result, attempt, errors_per_attempt
        params = result.get("params", {})
        if params.get("needs_clarification"):
            errors_per_attempt.append(["needs_clarification"])
            return result, attempt, errors_per_attempt
        validation = validate_tool_params(result, register)
        if validation.ok:
            errors_per_attempt.append([])
            return result, attempt, errors_per_attempt
        errors_per_attempt.append(list(validation.errors))
        feedback = (
            "Your previous tool call had invalid enum values. "
            "FIX by copying exact strings from the enum lists in the tool schema. "
            "Do NOT translate, lowercase, or paraphrase.\n"
            f"Previous args: {json.dumps(result.get('args', {}), ensure_ascii=False)}\n"
            f"Errors:\n" + "\n".join(f"- {e}" for e in validation.errors)
        )
    return result, MAX_VALIDATION_RETRIES, errors_per_attempt


async def run_case(
    case: CalibrationCase, register: dict, *,
    model: str, base_url: str, api_key: str, verbose: bool,
) -> tuple[bool, str]:
    """Run one case. Returns (passed, reason_if_failed)."""
    print(f"[{case.category:11}] Q: {case.question}")
    if case.note:
        print(f"              note: {case.note}")

    result, attempts, err_log = await _call_with_self_healing(
        case.question, register,
        model=model, base_url=base_url, api_key=api_key,
    )

    if attempts > 1:
        print(f"              attempts: {attempts}")
        for i, errs in enumerate(err_log[:-1], 1):
            if errs:
                print(f"                  try {i}: {errs}")

    final_errs = err_log[-1] if err_log else ["no result"]
    actual_args = result.get("args", {})
    params = result.get("params", {})

    if verbose:
        print(f"              args: {json.dumps(actual_args, ensure_ascii=False)}")

    # Degraded cases: success means either auto-recovered or surfaced as clarification.
    if case.category == "degraded":
        if final_errs == [] and not params.get("needs_clarification"):
            print(f"              PASS (auto-recovered in {attempts})")
            return True, ""
        if params.get("needs_clarification") or "needs_clarification" in final_errs:
            print(f"              PASS (clarification requested — expected for degraded)")
            return True, ""
        reason = f"did not recover: {final_errs}"
        print(f"              FAIL ({reason})")
        return False, reason

    # Non-degraded: check tool + params.
    if result.get("error"):
        reason = f"model error: {result.get('error')}"
        print(f"              FAIL ({reason})")
        return False, reason

    if final_errs and final_errs != []:
        reason = f"validation not ok: {final_errs}"
        print(f"              FAIL ({reason})")
        return False, reason

    tool_ok = result.get("tool") == case.expected_mode
    if not tool_ok:
        reason = f"wrong mode (expected {case.expected_mode}, got {result.get('tool')!r})"
        print(f"              FAIL ({reason})")
        return False, reason

    param_errs = check_params(case.expected_args, actual_args)
    if param_errs:
        print(f"              FAIL (param mismatch):")
        for e in param_errs:
            print(f"                {e}")
        return False, "param mismatch"

    print(f"              PASS")
    return True, ""


async def run(args) -> bool:
    register = load_register(args.register)
    print(f"Register:  {register['name']}")
    print(f"  dims:    {[d['name'] for d in register.get('dimensions', [])]}")
    print(f"  res:     {[r['name'] for r in register.get('resources', [])]}")
    print(f"Model:     {args.model}")
    print(f"Base URL:  {args.url}")
    print(f"Period:    {args.year}-{args.month:02d}")
    print()

    cases = generate_cases(
        register,
        year=args.year, month=args.month,
        typo_variants_per_base=args.typos_per_base,
        include_declensions=not args.no_declensions,
        include_typos=not args.no_typos,
        include_degraded=not args.no_degraded,
        seed=args.seed,
    )
    print(f"Generated {len(cases)} test cases "
          f"({Counter(c.category for c in cases)})")
    print()

    if args.verbose:
        tools = build_tools(register)
        print("=== Tool schema ===")
        print(json.dumps(tools, ensure_ascii=False, indent=2))
        print()

    results: dict[str, list[bool]] = {}
    for case in cases:
        ok, _ = await run_case(
            case, register,
            model=args.model, base_url=args.url, api_key=args.api_key,
            verbose=args.verbose,
        )
        results.setdefault(case.category, []).append(ok)
        print()

    total = sum(len(v) for v in results.values())
    passed = sum(sum(v) for v in results.values())
    print("=== Summary ===")
    for cat in ("base", "declension", "typo", "degraded"):
        lst = results.get(cat)
        if not lst:
            continue
        print(f"  {cat:11}: {sum(lst)}/{len(lst)}")
    print(f"  {'OVERALL':11}: {passed}/{total}")
    return passed == total


def main():
    parser = argparse.ArgumentParser(
        description="Calibrate tool calling against a real register with morph/typo variations.",
    )
    parser.add_argument("--model", default=settings.model_name,
                        help=f"Model name (env: MODEL_NAME, default {settings.model_name})")
    parser.add_argument("--url", default=settings.ollama_base_url,
                        help=f"Base URL (env: OLLAMA_BASE_URL, default {settings.ollama_base_url})")
    parser.add_argument("--api-key", default=settings.openai_api_key,
                        help="API key for OpenAI-compatible endpoint (env: OPENAI_API_KEY)")
    parser.add_argument("--register", default=None,
                        help="Register name (default: first register in metadata.db)")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--month", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--typos-per-base", type=int, default=1)
    parser.add_argument("--no-declensions", action="store_true")
    parser.add_argument("--no-typos", action="store_true")
    parser.add_argument("--no-degraded", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    ok = asyncio.run(run(args))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
