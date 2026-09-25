"""Small RawTree HTTP client. Tables appear on first insert."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

_SSL = ssl.create_default_context(cafile="/etc/ssl/cert.pem")


class RawTreeError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message

    @property
    def missing_table(self) -> bool:
        return "table not found" in self.message.lower()


class RawTree:
    def __init__(self, api_key: str, base_url: str = "https://api.rawtree.com"):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def insert(self, table: str, rows: list[dict[str, Any]]) -> int:
        body = self._request("POST", f"/v1/tables/{table}", rows)
        return int(body.get("inserted", len(rows)))

    def query(self, sql: str) -> list[dict[str, Any]]:
        body = self._request("POST", "/v1/query", {"sql": sql})
        return list(body.get("data") or [])

    def _request(self, method: str, path: str, payload: Any) -> dict[str, Any]:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self._base_url + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, context=_SSL, timeout=30) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            message = detail
            try:
                parsed = json.loads(detail)
                message = parsed.get("message") or parsed.get("error") or detail
            except json.JSONDecodeError:
                pass
            raise RawTreeError(exc.code, message) from exc
        if not raw:
            return {}
        return json.loads(raw)
