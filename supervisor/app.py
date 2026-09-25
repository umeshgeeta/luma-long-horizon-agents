"""Supervisor page. Speaks to Horizon over MCP and starts the Nimble wrapper as a process."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from horizon_client import call_tool

HERE = Path(__file__).resolve().parent
PAGE = (HERE / "index.html").read_text()
HOST = "127.0.0.1"
PORT = int(os.environ.get("SUPERVISOR_PORT", "8780"))
HORIZON_URL = os.environ.get("HORIZON_URL", "http://127.0.0.1:8765/mcp")
WRAPPER = Path(os.environ.get("NIMBLE_WRAPPER", str(HERE.parent / "nimble_session" / "session.py")))
NIMBLE_CONFIG = Path(os.environ.get("NIMBLE_CONFIG", str(HERE.parent / "src" / "config.json")))


def wants_nimble(text: str) -> bool:
    lowered = text.lower()
    return "search" in lowered or "nimble" in lowered or "nimbel" in lowered


PROCESSES: dict[str, subprocess.Popen] = {}
PROCESS_LOCK = threading.Lock()


def watch_wrapper(proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.decode().rstrip()
        print(f"[nimble] {text}", flush=True)
        if text.startswith("registered "):
            agent_id = text.split(" ", 1)[1].strip()
            with PROCESS_LOCK:
                PROCESSES[agent_id] = proc


def stop_wrapper(agent_id: str) -> None:
    with PROCESS_LOCK:
        proc = PROCESSES.pop(agent_id, None)
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._bytes(200, PAGE.encode(), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/agents":
            self._json(asyncio.run(call_tool("list_agents")))
            return
        if parsed.path == "/api/timeline":
            agent_id = parse_qs(parsed.query).get("agent_id", [""])[0]
            if not agent_id:
                self._json({"error": "agent_id is required"}, status=400)
                return
            self._json(asyncio.run(call_tool("get_timeline", {"agent_id": agent_id})))
            return
        self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, status=400)
            return
        if parsed.path == "/api/launch":
            self._launch(str(body.get("instruction") or ""))
            return
        if parsed.path == "/api/compact":
            agent_id = str(body.get("agent_id") or "")
            if not agent_id:
                self._json({"error": "agent_id is required"}, status=400)
                return
            self._json(asyncio.run(call_tool("compact", {"agent_id": agent_id})))
            return
        if parsed.path == "/api/terminate":
            agent_id = str(body.get("agent_id") or "")
            if not agent_id:
                self._json({"error": "agent_id is required"}, status=400)
                return
            marked = asyncio.run(call_tool("terminate_agent", {"agent_id": agent_id}))
            stop_wrapper(agent_id)
            self._json(marked)
            return
        self._json({"error": "not found"}, status=404)

    def _launch(self, instruction: str) -> None:
        text = " ".join(instruction.split())
        if not text or not wants_nimble(text):
            self._json(
                {
                    "ok": False,
                    "message": "Phrase the instruction as a Nimble search. The sentence becomes the session goal.",
                }
            )
            return
        if not WRAPPER.is_file():
            self._json({"ok": False, "message": f"Nimble wrapper not found at {WRAPPER}"}, status=500)
            return
        if not NIMBLE_CONFIG.is_file():
            self._json({"ok": False, "message": f"Nimble config not found at {NIMBLE_CONFIG}"}, status=500)
            return
        proc = subprocess.Popen(
            [
                sys.executable,
                str(WRAPPER),
                "--horizon",
                HORIZON_URL,
                "--goal",
                text,
                "--config",
                str(NIMBLE_CONFIG),
            ],
            cwd=str(WRAPPER.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        threading.Thread(target=watch_wrapper, args=(proc,), daemon=True).start()
        self._json({"ok": True, "message": "Started a long-running Nimble search. Refresh to watch it. Terminate stops it."})

    def _json(self, payload: dict, status: int = 200) -> None:
        self._bytes(status, json.dumps(payload).encode(), "application/json")

    def _bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[supervisor] {self.address_string()} {fmt % args}", flush=True)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"supervisor http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
