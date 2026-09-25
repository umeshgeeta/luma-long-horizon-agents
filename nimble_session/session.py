"""Long-running Nimble search session. Talks to Horizon only over MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import time
import urllib.request
from pathlib import Path

from mcp import Client

_SSL = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
_SEARCH_URL = "https://sdk.nimbleway.com/v2/search"
_TEXT_LIMIT = 700


def search(api_key: str, query: str) -> dict:
    payload = json.dumps({"query": query, "max_results": 2, "search_depth": "fast"}).encode()
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


def event_body(found: dict) -> str:
    blocks = []
    for item in found["results"]:
        blocks.append("\n".join(part for part in (item["title"], item["url"], item["text"]) if part))
    return "\n\n".join(blocks)


def as_dict(result) -> dict:
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured:
        return structured
    return json.loads(result.content[0].text)


_INTERVAL_SECONDS = 8
_SUFFIXES = (
    "",
    " reliability over long tasks",
    " what state should persist",
    " recent developments",
)


def next_query(goal: str, pass_no: int) -> str:
    suffix = _SUFFIXES[(pass_no - 1) % len(_SUFFIXES)]
    query = f"{goal}{suffix}".strip()
    if pass_no > len(_SUFFIXES):
        query = f"{query} {pass_no}"
    return query


async def run(horizon_url: str, api_key: str, goal: str) -> None:
    async with Client(horizon_url, read_timeout_seconds=60) as client:
        registered = as_dict(
            await client.call_tool(
                "register_agent",
                {"name": "nimble-research", "goal": goal},
            )
        )
        agent_id = registered["agent_id"]
        print(f"registered {agent_id}", flush=True)
        pass_no = 1
        while True:
            query = next_query(goal, pass_no)
            found = search(api_key, query)
            titles = "; ".join(item["title"] for item in found["results"] if item["title"])
            print(f"searched {query}", flush=True)
            print(f"  {titles}", flush=True)
            result = await client.call_tool(
                "append_event",
                {
                    "agent_id": agent_id,
                    "kind": "observation",
                    "summary": f"Search: {query}",
                    "body": event_body(found),
                },
            )
            if getattr(result, "is_error", False) or getattr(result, "isError", False):
                print(f"stopped {agent_id}", flush=True)
                return
            pass_no += 1
            time.sleep(_INTERVAL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a Nimble search session with Horizon.")
    parser.add_argument("--horizon", required=True, help="Horizon MCP URL, for example http://127.0.0.1:8765/mcp")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--config", required=True, help="JSON file with nimble_api_key")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    asyncio.run(run(args.horizon, config["nimble_api_key"], args.goal.strip()))


if __name__ == "__main__":
    main()
