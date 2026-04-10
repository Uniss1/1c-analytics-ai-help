"""Gemma 4 E2B tool calling via OpenAI-compatible API (Open WebUI / Ollama).

Sends user question with tool definitions, parses tool_calls response.
Returns structured params compatible with query_builder.build_query().
"""

import json
import logging

import httpx

from .config import settings
from .tool_defs import build_system_message, build_tools, key_to_dim

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 3


async def call_with_tools(
    question: str,
    register_metadata: dict,
    *,
    model: str | None = None,
    temperature: float = 0.1,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Call model via OpenAI-compatible /v1/chat/completions with tools.

    Returns:
        {
            "tool": str — selected tool name (aggregate/group_by/top_n/time_series),
            "args": dict — tool arguments filled by model,
            "params": dict — normalized params for query_builder,
            "raw_response": dict — full API response for debugging,
        }
        Or on failure:
        {
            "tool": None,
            "error": str,
            "raw_response": dict | str,
        }
    """
    url = base_url or settings.openai_base_url or "http://localhost:3000"
    key = api_key or settings.openai_api_key or ""
    tools = build_tools(register_metadata)
    system_msg = build_system_message(register_metadata)
    model_name = model or settings.model_name

    # Convert tools from Ollama format to OpenAI format (same structure)
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": question},
        ],
        "tools": tools,
        "tool_choice": "required",
        "temperature": temperature,
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.post(
                    f"{url.rstrip('/')}/api/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPError as e:
                logger.error("API HTTP error (attempt %d): %s", attempt, e)
                if attempt < MAX_RETRIES:
                    import asyncio
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                return {"tool": None, "error": str(e), "raw_response": ""}

            data = response.json()
            parsed = _parse_response(data, register_metadata)

            # If model returned a valid tool call, we're done
            if parsed.get("tool") is not None and "error" not in parsed:
                return parsed

            # No tool call — retry with reinforcement message
            if attempt < MAX_RETRIES:
                logger.warning(
                    "No tool call on attempt %d, retrying with reinforcement", attempt
                )
                payload["messages"].append({
                    "role": "assistant",
                    "content": parsed.get("error", ""),
                })
                payload["messages"].append({
                    "role": "user",
                    "content": "You MUST call one of the provided tools. Do NOT respond with text. Call a tool now.",
                })
                continue

            return parsed

    return {"tool": None, "error": "Max retries exceeded", "raw_response": ""}


def _parse_response(data: dict, register_metadata: dict) -> dict:
    """Parse OpenAI-compatible chat response with tool calls."""
    choices = data.get("choices", [])
    if not choices:
        return {
            "tool": None,
            "error": "Empty choices in response",
            "raw_response": data,
        }

    message = choices[0].get("message", {})
    tool_calls = message.get("tool_calls", [])

    if not tool_calls:
        content = message.get("content", "")
        logger.warning("No tool_calls in response. Content: %s", content[:300])
        return {
            "tool": None,
            "error": f"Model responded with text instead of tool call: {content[:300]}",
            "raw_response": data,
        }

    # Take the first tool call
    tc = tool_calls[0]
    func = tc.get("function", {})
    tool_name = func.get("name", "")
    arguments = func.get("arguments", {})

    # Parse arguments if string (OpenAI format returns JSON string)
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {
                "tool": tool_name,
                "error": f"Failed to parse arguments JSON: {arguments[:200]}",
                "raw_response": data,
            }

    # Normalize to query_builder format
    params = _normalize_params(tool_name, arguments, register_metadata)

    return {
        "tool": tool_name,
        "args": arguments,
        "params": params,
        "raw_response": data,
    }


def _normalize_params(tool_name: str, args: dict, register_metadata: dict) -> dict:
    """Convert tool call arguments to query_builder.build_query() format.

    Tool args use Latin keys (metric, scenario, company, year, month).
    query_builder expects 1C names (Показатель, Сценарий, ДЗО) + period dict.
    """
    resource = args.get("resource", "Сумма")
    year = args.get("year")
    month = args.get("month")
    group_by_latin = args.get("group_by")
    order_by = args.get("order", args.get("order_by", "desc"))
    limit = args.get("limit", 1000)

    # Build period from flat year/month
    period = {}
    if year is not None and month is not None:
        period = {"year": year, "month": month}

    # Convert Latin filter keys → 1C dimension names
    skip_keys = {
        "resource", "year", "month", "group_by", "order", "order_by", "limit",
        "compare_by", "values", "numerator", "denominator",
        "condition_operator", "condition_value",
    }
    filters = {}
    for k, v in args.items():
        if k in skip_keys or v is None:
            continue
        dim_name = key_to_dim(k)
        filters[dim_name] = v

    # Apply defaults for required dimensions not provided
    for dim in register_metadata.get("dimensions", []):
        name = dim["name"]
        if dim.get("filter_type") in ("year_month", "range"):
            continue
        if name not in filters and dim.get("default_value"):
            filters[name] = dim["default_value"]

    # group_by: convert Latin key to 1C name
    group_by = []
    if group_by_latin:
        group_by = [key_to_dim(group_by_latin)]

    # Top N defaults
    if tool_name == "top_n":
        limit = limit if limit != 1000 else 10

    # Tool-specific params for new tools
    extra = {}
    if tool_name == "compare":
        extra["compare_by"] = key_to_dim(args.get("compare_by", ""))
        extra["values"] = args.get("values", [])
    elif tool_name == "ratio":
        extra["numerator"] = args.get("numerator", "")
        extra["denominator"] = args.get("denominator", "")
    elif tool_name == "filtered":
        extra["condition_operator"] = args.get("condition_operator", ">")
        extra["condition_value"] = args.get("condition_value", 0)

    # Determine needs_clarification
    needs_clarification = False
    missing = []
    for dim in register_metadata.get("dimensions", []):
        name = dim["name"]
        if not dim.get("required"):
            continue
        if dim.get("default_value"):
            continue
        ft = dim.get("filter_type", "=")
        if ft in ("year_month", "range"):
            if not period.get("year"):
                missing.append(name)
        elif ft == "=":
            # For compare tool, the compare_by dimension is covered by values
            if tool_name == "compare" and name == extra.get("compare_by"):
                continue
            if name not in filters and name not in group_by:
                missing.append(name)

    if missing:
        needs_clarification = True

    result = {
        "resource": resource,
        "filters": filters,
        "period": period,
        "group_by": group_by,
        "order_by": order_by,
        "limit": limit,
        "needs_clarification": needs_clarification,
        "understood": {
            "описание": f"tool={tool_name}, resource={resource}",
        },
    }
    result.update(extra)
    return result
