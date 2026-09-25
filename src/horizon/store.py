"""Session log. A checkpoint hides older events; the rows stay in RawTree."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from horizon.liquid import compact_state
from horizon.rawtree import RawTree, RawTreeError

EVENTS = "horizon_events"
CHECKPOINTS = "horizon_checkpoints"
SESSIONS = "horizon_sessions"
TERMINATIONS = "horizon_terminations"


def sql_str(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SessionLog:
    def __init__(self, db: RawTree):
        self.db = db
        # RawTree reads can lag a fresh insert, so seq and the latest
        # checkpoint are tracked in-process after they are written.
        self._last_seq: dict[str, int] = {}
        self._checkpoints: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._terminated: set[str] = set()
        self._stamped_terminated = False

    def register(self, name: str, goal: str) -> dict[str, Any]:
        agent_id = str(uuid.uuid4())
        record = {
            "agent_id": agent_id,
            "name": name,
            "goal": goal,
            "created_at": now_iso(),
            "state": "active",
        }
        self.db.insert(SESSIONS, [record])
        self._sessions[agent_id] = record
        return {"agent_id": agent_id, "name": name, "goal": goal}

    def list_agents(self) -> dict[str, Any]:
        rows = self._session_rows()
        self._stamp_terminated_states(rows)
        by_id: dict[str, dict[str, Any]] = {}
        for row in list(self._sessions.values()) + rows:
            agent_id = str(row.get("agent_id") or "")
            if not agent_id:
                continue
            incoming = {
                "agent_id": agent_id,
                "name": row.get("name") or "",
                "goal": row.get("goal") or "",
                "created_at": str(row.get("created_at") or ""),
                "state": str(row.get("state") or "active"),
            }
            current = by_id.get(agent_id)
            if current is None or incoming["created_at"] >= current["created_at"]:
                by_id[agent_id] = incoming
        terminated = self._terminated_ids()
        agents = [
            item
            for item in by_id.values()
            if item["agent_id"] not in terminated and item["state"] != "terminated"
        ]
        agents.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return {"agents": agents}

    def terminate(self, agent_id: str) -> dict[str, Any]:
        if not self._is_terminated(agent_id):
            session = self._session(agent_id)
            created_at = now_iso()
            self.db.insert(
                SESSIONS,
                [
                    {
                        "agent_id": agent_id,
                        "name": session.get("name") or "",
                        "goal": session.get("goal") or "",
                        "created_at": created_at,
                        "state": "terminated",
                    }
                ],
            )
            self.db.insert(
                TERMINATIONS,
                [{"agent_id": agent_id, "state": "terminated", "created_at": created_at}],
            )
            self._terminated.add(agent_id)
            if agent_id in self._sessions:
                self._sessions[agent_id]["state"] = "terminated"
        return {"agent_id": agent_id, "terminated": True, "state": "terminated"}

    def append_event(self, agent_id: str, kind: str, summary: str, body: str = "") -> dict[str, Any]:
        if self._is_terminated(agent_id):
            raise RuntimeError(f"session {agent_id} is terminated")
        seq = self._next_seq(agent_id)
        event = {
            "agent_id": agent_id,
            "seq": seq,
            "kind": kind,
            "summary": summary,
            "body": body,
            "ts": now_iso(),
        }
        self.db.insert(EVENTS, [event])
        return event

    def get_timeline(self, agent_id: str) -> dict[str, Any]:
        checkpoint = self._latest_checkpoint(agent_id)
        cutoff = int(checkpoint["cutoff_seq"]) if checkpoint else 0
        agent = sql_str(agent_id)
        events = self._query(
            f"""
            SELECT seq, kind, summary, body, ts
            FROM {EVENTS}
            WHERE agent_id = {agent} AND seq > {cutoff}
            ORDER BY seq
            """
        )
        hidden_rows = self._query(
            f"""
            SELECT count() AS n
            FROM {EVENTS}
            WHERE agent_id = {agent} AND seq <= {cutoff}
            """
        )
        hidden = int(hidden_rows[0]["n"]) if hidden_rows else 0
        working_state = None
        if checkpoint and checkpoint.get("working_state"):
            working_state = json.loads(checkpoint["working_state"])
        return {
            "agent_id": agent_id,
            "working_state": working_state,
            "events": events,
            "visible_count": len(events),
            "hidden_count": hidden,
            "cutoff_seq": cutoff,
        }

    def compact(self, agent_id: str) -> dict[str, Any]:
        """Fold every visible event into a working state with LFM2.5 and hide that prefix."""
        timeline = self.get_timeline(agent_id)
        if timeline["visible_count"] == 0:
            return {
                "agent_id": agent_id,
                "compacted": False,
                "hidden_count": timeline["hidden_count"],
                "working_state": timeline["working_state"],
            }

        cutoff = max(int(event["seq"]) for event in timeline["events"])
        session = self._session(agent_id)
        prior = timeline["working_state"] or {}
        goal = session.get("goal") or prior.get("goal") or ""
        working_state = compact_state(goal, prior, timeline["events"])
        checkpoint_id = str(uuid.uuid4())
        created_at = now_iso()
        hidden_count = timeline["hidden_count"] + timeline["visible_count"]
        self.db.insert(
            CHECKPOINTS,
            [
                {
                    "agent_id": agent_id,
                    "checkpoint_id": checkpoint_id,
                    "cutoff_seq": cutoff,
                    "working_state": json.dumps(working_state),
                    "hidden_count": hidden_count,
                    "created_at": created_at,
                }
            ],
        )
        self._checkpoints[agent_id] = {
            "checkpoint_id": checkpoint_id,
            "cutoff_seq": cutoff,
            "working_state": json.dumps(working_state),
            "created_at": created_at,
        }
        return {
            "agent_id": agent_id,
            "compacted": True,
            "checkpoint_id": checkpoint_id,
            "cutoff_seq": cutoff,
            "hidden_count": timeline["hidden_count"] + timeline["visible_count"],
            "working_state": working_state,
        }

    def _next_seq(self, agent_id: str) -> int:
        if agent_id in self._last_seq:
            self._last_seq[agent_id] += 1
            return self._last_seq[agent_id]
        rows = self._query(
            f"SELECT max(seq) AS n FROM {EVENTS} WHERE agent_id = {sql_str(agent_id)}"
        )
        current = 0
        if rows and rows[0].get("n") is not None:
            current = int(rows[0]["n"])
        self._last_seq[agent_id] = current + 1
        return self._last_seq[agent_id]

    def _latest_checkpoint(self, agent_id: str) -> dict[str, Any] | None:
        rows = self._query(
            f"""
            SELECT checkpoint_id, cutoff_seq, working_state, created_at
            FROM {CHECKPOINTS}
            WHERE agent_id = {sql_str(agent_id)}
            ORDER BY cutoff_seq DESC
            LIMIT 1
            """
        )
        stored = rows[0] if rows else None
        cached = self._checkpoints.get(agent_id)
        if cached and (stored is None or int(cached["cutoff_seq"]) >= int(stored["cutoff_seq"])):
            return cached
        return stored

    def _terminated_ids(self) -> set[str]:
        rows = self._query(f"SELECT agent_id FROM {TERMINATIONS}")
        found = set(self._terminated)
        for row in rows:
            agent_id = str(row.get("agent_id") or "")
            if agent_id:
                found.add(agent_id)
        self._terminated = found
        return found

    def _is_terminated(self, agent_id: str) -> bool:
        if agent_id in self._terminated:
            return True
        rows = self._query(
            f"SELECT agent_id FROM {TERMINATIONS} WHERE agent_id = {sql_str(agent_id)} LIMIT 1"
        )
        if rows:
            self._terminated.add(agent_id)
            return True
        return False

    def _session(self, agent_id: str) -> dict[str, Any]:
        rows = self._query(
            f"""
            SELECT agent_id, name, goal
            FROM {SESSIONS}
            WHERE agent_id = {sql_str(agent_id)}
            LIMIT 1
            """
        )
        return rows[0] if rows else {}

    def _session_rows(self) -> list[dict[str, Any]]:
        try:
            return self._query(
                f"""
                SELECT agent_id, name, goal, created_at, state
                FROM {SESSIONS}
                ORDER BY created_at DESC
                """
            )
        except RawTreeError as exc:
            if "state" not in exc.message.lower():
                raise
            return self._query(
                f"""
                SELECT agent_id, name, goal, created_at
                FROM {SESSIONS}
                ORDER BY created_at DESC
                """
            )

    def _stamp_terminated_states(self, rows: list[dict[str, Any]]) -> None:
        """Write state=terminated onto sessions that were ended before that field existed."""
        if self._stamped_terminated:
            return
        self._stamped_terminated = True
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            agent_id = str(row.get("agent_id") or "")
            if not agent_id:
                continue
            created_at = str(row.get("created_at") or "")
            current = latest.get(agent_id)
            if current is None or created_at >= str(current.get("created_at") or ""):
                latest[agent_id] = row
        pending = []
        created_at = now_iso()
        for agent_id in self._terminated_ids():
            current = latest.get(agent_id) or {}
            if str(current.get("state") or "") == "terminated":
                continue
            pending.append(
                {
                    "agent_id": agent_id,
                    "name": current.get("name") or "",
                    "goal": current.get("goal") or "",
                    "created_at": created_at,
                    "state": "terminated",
                }
            )
        if pending:
            self.db.insert(SESSIONS, pending)

    def _query(self, sql: str) -> list[dict[str, Any]]:
        try:
            return self.db.query(sql)
        except RawTreeError as exc:
            if exc.missing_table:
                return []
            raise
