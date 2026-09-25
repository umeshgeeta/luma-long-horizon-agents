"""Call the four MCP tools over stdio against the live RawTree log."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SRC = Path(__file__).resolve().parent


def payload(result) -> dict:
    if getattr(result, "structured_content", None):
        return result.structured_content
    text = result.content[0].text
    return json.loads(text)


def show(label: str, timeline: dict) -> None:
    state = timeline.get("working_state")
    print(f"\n{label}")
    print(f"  visible={timeline['visible_count']}  hidden={timeline['hidden_count']}")
    if state:
        print(f"  goal: {state.get('goal')}")
        print(f"  facts: {len(state.get('facts') or [])}  source: {state.get('source')}")
    for event in timeline["events"]:
        print(f"  #{event['seq']} {event['kind']}: {event['summary']}")


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SRC / "server.py")],
        cwd=str(SRC),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", ", ".join(tool.name for tool in tools.tools))

            registered = payload(
                await session.call_tool(
                    "register_agent",
                    {
                        "name": "mcp-demo",
                        "goal": "Compact a session through the MCP control plane.",
                    },
                )
            )
            agent_id = registered["agent_id"]
            print(f"registered {agent_id}")

            for summary in (
                "Search: the trace is the thing that grows.",
                "Decision: the supervisor compacts, the session does not.",
            ):
                kind = "decision" if summary.startswith("Decision") else "observation"
                await session.call_tool(
                    "append_event",
                    {"agent_id": agent_id, "kind": kind, "summary": summary, "body": "fixture"},
                )

            before = payload(await session.call_tool("get_timeline", {"agent_id": agent_id}))
            show("before compact", before)
            compacted = payload(await session.call_tool("compact", {"agent_id": agent_id}))
            print(f"\ncompact compacted={compacted['compacted']} hidden={compacted['hidden_count']}")
            after = payload(await session.call_tool("get_timeline", {"agent_id": agent_id}))
            show("after compact", after)


if __name__ == "__main__":
    asyncio.run(main())
