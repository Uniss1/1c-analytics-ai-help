"""Debug: see raw LLM response and why validation fails."""

import asyncio
import sys
sys.path.insert(0, ".")

from pathlib import Path

from api.llm_client import generate
from api.metadata import init_metadata, find_register
from api.date_parser import parse_period
from api.query_validator import validate_query

_PROMPT_PATH = Path("prompts/query_generator.txt")
_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


def _format_metadata(register_metadata: dict) -> str:
    lines = [f"Регистр: {register_metadata['name']}"]
    if register_metadata.get("description"):
        lines.append(f"Описание: {register_metadata['description']}")
    for dim in register_metadata.get("dimensions", []):
        lines.append(f"Измерение: {dim['name']} ({dim['data_type']})")
    for res in register_metadata.get("resources", []):
        lines.append(f"Ресурс: {res['name']} ({res['data_type']})")
    return "\n".join(lines)


def _parse_llm_response(response: str, question: str) -> dict:
    query = response.strip()
    if query.startswith("```"):
        lines = query.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        query = "\n".join(lines).strip()
    params = parse_period(question) or {}
    return {"query": query, "params": params}


async def main():
    question = sys.argv[1] if len(sys.argv) > 1 else "сравни Q1 и Q2 2025"

    init_metadata("metadata.db")
    meta = find_register(question)
    if not meta:
        print(f"Регистр не найден для: {question}")
        return

    print(f"=== Вопрос: {question}")
    print(f"=== Регистр: {meta['name']}")

    metadata_text = _format_metadata(meta)
    prompt = _SYSTEM_PROMPT.replace("{metadata}", metadata_text).replace(
        "{question}", question
    )

    print(f"\n=== Промпт для LLM ===")
    print(prompt)

    print(f"\n=== Сырой ответ LLM ===")
    response = await generate(role="query", system_prompt=prompt, user_message=question)
    print(repr(response))

    print(f"\n=== После парсинга ===")
    result = _parse_llm_response(response, question)
    print(f"query: {repr(result['query'])}")
    print(f"params: {result['params']}")

    print(f"\n=== Валидация ===")
    allowed = {meta["name"]}
    is_valid, error, sanitized = validate_query(result["query"], allowed)
    print(f"valid: {is_valid}")
    print(f"error: {error}")
    print(f"sanitized: {sanitized}")


asyncio.run(main())
