"""Supervisor MCP. Exposes the session log; it does not search or compact with a model."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.mcpserver import MCPServer

from horizon.config import load_config
from horizon.rawtree import RawTree
from horizon.store import SessionLog

mcp = MCPServer(
    "horizon-control",
    instructions=(
        "Control plane for a long-horizon research session stored in RawTree. "
        "Register a session, append events, read the bounded timeline, and compact "
        "the visible prefix into a retained working state. Raw events stay in the "
        "database; later timeline reads hide them."
    ),
)

_log: SessionLog | None = None


def log() -> SessionLog:
    global _log
    if _log is None:
        _log = SessionLog(RawTree(load_config()["rawtree_api_key"]))
    return _log


@mcp.tool()
def list_agents() -> dict:
    """List registered sessions with agent_id, name, goal, and created_at."""
    return log().list_agents()


@mcp.tool()
def register_agent(name: str, goal: str) -> dict:
    """Register one research session. Other tools take the returned agent_id."""
    return log().register(name, goal)


@mcp.tool()
def append_event(agent_id: str, kind: str, summary: str, body: str = "") -> dict:
    """Append one event. kind is observation, action, decision, or artifact."""
    return log().append_event(agent_id, kind, summary, body)


@mcp.tool()
def get_timeline(agent_id: str) -> dict:
    """Return the working state plus events since the last checkpoint, and hidden count."""
    return log().get_timeline(agent_id)


@mcp.tool()
def compact(agent_id: str) -> dict:
    """Fold every visible event into the working state and hide that prefix."""
    return log().compact(agent_id)


@mcp.tool()
def terminate_agent(agent_id: str) -> dict:
    """Stop managing a session. Later appends are refused and it leaves the list."""
    return log().terminate(agent_id)


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http", host="127.0.0.1", port=8765)
    else:
        mcp.run(transport="stdio")
