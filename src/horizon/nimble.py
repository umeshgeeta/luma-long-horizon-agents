"""Nimble web search for the research client. The control-plane MCP does not call this."""

from __future__ import annotations

import json
import ssl
import urllib.request
from typing import Any

_SSL = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
_SEARCH_URL = "https://sdk.nimbleway.com/v2/search"
_TEXT_LIMIT = 700


def search(api_key: str, query: str, max_results: int = 2, search_depth: str = "fast") -> dict[str, Any]:
    payload = json.dumps(
        {"query": query, "max_results": max_results, "search_depth": search_depth}
    ).encode()
    req = urllib.request.Request(
        _SEARCH_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, context=_SSL, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    results = []
    for item in data.get("results") or []:
        text = (item.get("content") or item.get("description") or "").strip()
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "text": text[:_TEXT_LIMIT],
            }
        )
    return {"query": query, "results": results}


def event_body(found: dict[str, Any]) -> str:
    blocks = []
    for item in found["results"]:
        blocks.append("\n".join(part for part in (item["title"], item["url"], item["text"]) if part))
    return "\n\n".join(blocks)
