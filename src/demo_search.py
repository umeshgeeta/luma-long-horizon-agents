"""Research client: Nimble search outside MCP, then supervise that session through MCP."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from horizon.config import load_config
from horizon.nimble import event_body, search

SRC = Path(__file__).resolve().parent

QUERIES = [
    "why long-horizon AI agents lose reliability",
    "agent memory compaction versus keeping the full history",
    "what state should persist when an agent trace is pruned",
]


def payload(result) -> dict:
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text)


def show(label: str, timeline: dict) -> None:
    state = timeline.get("working_state")
    print(f"\n{label}")
    print(f"  visible={timeline['visible_count']}  hidden={timeline['hidden_count']}")
    if state:
        print(f"  goal: {state.get('goal')}")
        print(f"  source: {state.get('source')}")
        for fact in state.get("facts") or []:
            print(f"  fact: {fact}")
        for decision in state.get("decisions") or []:
            print(f"  decision: {decision}")
    for event in timeline["events"]:
        print(f"  #{event['seq']} {event['kind']}: {event['summary']}")


async def main() -> None:
    cfg = load_config()
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SRC / "server.py")],
        cwd=str(SRC),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            registered = payload(
                await session.call_tool(
                    "register_agent",
                    {
                        "name": "nimble-research",
                        "goal": "Find what a long-horizon agent must retain after its search trace is compacted.",
                    },
                )
            )
            agent_id = registered["agent_id"]
            print(f"registered search session {agent_id}")

            for query in QUERIES:
                found = search(cfg["nimble_api_key"], query)
                titles = "; ".join(item["title"] for item in found["results"] if item["title"])
                print(f"searched {query}")
                print(f"  {len(found['results'])} results: {titles}")
                await session.call_tool(
                    "append_event",
                    {
                        "agent_id": agent_id,
                        "kind": "observation",
                        "summary": f"Search: {query}",
                        "body": event_body(found),
                    },
                )

            before = payload(await session.call_tool("get_timeline", {"agent_id": agent_id}))
            show("before compact", before)
            compacted = payload(
                await session.call_tool(
                    "compact",
                    {"agent_id": agent_id},
                    read_timeout_seconds=180,
                )
            )
            print(f"\ncompact compacted={compacted['compacted']} hidden={compacted['hidden_count']}")
            after = payload(await session.call_tool("get_timeline", {"agent_id": agent_id}))
            show("after compact", after)


if __name__ == "__main__":
    asyncio.run(main())
