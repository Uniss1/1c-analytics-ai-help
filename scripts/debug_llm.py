#!/usr/bin/env python3
"""Debug: see raw LLM response and why validation fails.

Usage: python3 scripts/debug_llm.py "какая выручка за март"
Run from project root.
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "api"


def _load(name, path):
    """Import a single module by file path, no package resolution."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load modules individually to avoid circular api package init
config = _load("api.config", API / "config.py")
date_parser = _load("api.date_parser", API / "date_parser.py")
llm_client = _load("api.llm_client", API / "llm_client.py")
metadata = _load("api.metadata", API / "metadata.py")
validator = _load("api.query_validator", API / "query_validator.py")

SYSTEM_PROMPT = (ROOT / "prompts" / "query_generator.txt").read_text(encoding="utf-8")


def format_metadata(meta: dict) -> str:
    lines = [f"Регистр: {meta['name']}"]
    if meta.get("description"):
        lines.append(f"Описание: {meta['description']}")
    for dim in meta.get("dimensions", []):
        lines.append(f"Измерение: {dim['name']} ({dim['data_type']})")
    for res in meta.get("resources", []):
        lines.append(f"Ресурс: {res['name']} ({res['data_type']})")
    return "\n".join(lines)


def parse_response(response: str, question: str) -> dict:
    query = response.strip()
    if query.startswith("```"):
        lines = query.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        query = "\n".join(lines).strip()
    params = date_parser.parse_period(question) or {}
    return {"query": query, "params": params}


async def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "сравни Q1 и Q2 2025"

    metadata.init_metadata(str(ROOT / "metadata.db"))
    meta = metadata.find_register(question)
    if not meta:
        print(f"Регистр не найден для: {question}")
        return

    print(f"=== Вопрос: {question}")
    print(f"=== Регистр: {meta['name']}")

    metadata_text = format_metadata(meta)
    prompt = SYSTEM_PROMPT.replace("{metadata}", metadata_text).replace(
        "{question}", question
    )

    print(f"\n=== Промпт для LLM ===")
    print(prompt)

    print(f"\n=== Сырой HTTP ответ ===")
    import httpx as _httpx
    url = config.settings.gpu_url("query")
    async with _httpx.AsyncClient(timeout=300) as client:
        raw = await client.post(f"{url}/api/generate", json={
            "model": config.settings.model_name,
            "system": prompt,
            "prompt": question,
            "stream": False,
        })
        data = raw.json()
        print(f"done_reason: {data.get('done_reason')}")
        print(f"response length: {len(data.get('response', ''))}")
        print(f"response: {repr(data.get('response', '')[:500])}")

    print(f"\n=== Через llm_client.generate (с retry) ===")
    import logging
    logging.basicConfig(level=logging.WARNING)
    response = await llm_client.generate(
        role="query", system_prompt=prompt, user_message=question
    )
    print(repr(response))

    print(f"\n=== После парсинга ===")
    result = parse_response(response, question)
    print(f"query: {repr(result['query'])}")
    print(f"params: {result['params']}")

    print(f"\n=== Валидация ===")
    allowed = {meta["name"]}
    is_valid, error, sanitized = validator.validate_query(result["query"], allowed)
    print(f"valid: {is_valid}")
    print(f"error: {error}")
    print(f"sanitized: {sanitized}")


asyncio.run(main())
