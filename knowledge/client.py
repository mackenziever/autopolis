"""Client HTTP Alveare (stdlib)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, List, Optional


class AlveareClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0, *, frozen: bool = False):
        self.base = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.frozen = frozen

    def _json(self, method: str, path: str, body: dict | None = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            return json.loads(r.read().decode())

    def health(self) -> dict:
        try:
            return self._json("GET", "/health")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {"ok": False, "error": str(exc)}

    def query(
        self,
        text: str,
        k: int = 4,
        source: str | None = None,
        *,
        tags: List[str] | None = None,
        agent_id: str | None = None,
        tick_min: int | None = None,
        tick_max: int | None = None,
    ) -> List[dict]:
        body: dict[str, Any] = {"text": text, "k": k}
        if source:
            body["source"] = source
        if tags:
            body["tags"] = list(tags)
        if agent_id:
            body["agent_id"] = agent_id
        if tick_min is not None:
            body["tick_min"] = tick_min
        if tick_max is not None:
            body["tick_max"] = tick_max
        try:
            out = self._json("POST", "/v1/query", body)
            return list(out.get("hits") or [])
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return []

    def upsert(
        self,
        text: str,
        *,
        source: str = "ops",
        tags: Optional[List[str]] = None,
        agent_id: str | None = None,
        tick: int | None = None,
        id: str | None = None,
    ) -> dict:
        if self.frozen:
            return {"ok": False, "error": "frozen_store", "frozen": True}
        body = {
            "text": text,
            "source": source,
            "tags": tags or [],
            "agent_id": agent_id,
            "tick": tick,
        }
        if id:
            body["id"] = id
        try:
            return self._json("POST", "/v1/upsert", body)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc)}

    def ingest_markdown(self, vault_path: str, limit_files: int | None = None) -> dict:
        if self.frozen:
            return {"ok": False, "error": "frozen_store", "frozen": True}
        body: dict[str, Any] = {"path": vault_path}
        if limit_files is not None:
            body["limit_files"] = limit_files
        try:
            return self._json("POST", "/v1/ingest/markdown", body)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc)}
