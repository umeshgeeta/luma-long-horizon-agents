"""MCP client for the supervisor page. No Horizon source imports."""

from __future__ import annotations

import json
import os

from mcp import Client

HORIZON_URL = os.environ.get("HORIZON_URL", "http://127.0.0.1:8765/mcp")


def as_dict(result) -> dict:
    if getattr(result, "is_error", False) or getattr(result, "isError", False):
        text = result.content[0].text if result.content else "tool call failed"
        raise RuntimeError(text)
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured:
        return structured
    return json.loads(result.content[0].text)


async def call_tool(name: str, arguments: dict | None = None) -> dict:
    async with Client(HORIZON_URL, read_timeout_seconds=180) as client:
        result = await client.call_tool(name, arguments or {})
        return as_dict(result)
