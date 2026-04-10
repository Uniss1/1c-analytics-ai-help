"""HTTP client for 1C Enterprise HTTP service."""

import httpx

from .config import settings


async def execute_query(query: str, params: dict) -> dict:
    """Execute 1C query via HTTP service.

    POST to 1C HTTP service with query text and parameters.
    Returns: {success: bool, data: list, total: int, truncated: bool, error: str|None}
    """
    async with httpx.AsyncClient(timeout=settings.query_timeout) as client:
        response = await client.post(
            f"{settings.onec_base_url}/query",
            json={"query": query, "params": params},
            auth=(settings.onec_user, settings.onec_password),
        )
        response.raise_for_status()
        return response.json()


async def execute_tool(tool_result: dict, register_name: str) -> dict:
    """Execute tool via 1C HTTP service (JSON params, no query text).

    POST to /analytics/execute with:
        {"register": str, "tool": str, "params": dict}

    Returns: 1C response dict:
        success case: {"success": True, "data": [...], "computed": {...}}
        error case:   {"success": False, "error_type": str, "error_message": str, ...}
    """
    payload = {
        "register": register_name,
        "tool": tool_result["tool"],
        "params": tool_result["params"],
    }

    async with httpx.AsyncClient(timeout=settings.query_timeout) as client:
        response = await client.post(
            f"{settings.onec_base_url}/analytics/execute",
            json=payload,
            auth=(settings.onec_user, settings.onec_password),
        )
        response.raise_for_status()
        return response.json()
