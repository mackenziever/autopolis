"""HTTP server Alveare (stdlib) — bind loopback/container, porta 9200."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from knowledge.alveare_store import AlveareStore
from knowledge.embedder import AlveareEmbedder
from knowledge.ingest_vault import ingest_vault

STORE: AlveareStore | None = None


def _frozen() -> bool:
    return os.getenv("CIVITAS_REPLAY", "").strip() in ("1", "true", "yes") or os.getenv(
        "CIVITAS_ALVEARE_FROZEN", ""
    ).strip() in ("1", "true", "yes")


def get_store() -> AlveareStore:
    global STORE
    if STORE is None:
        data = os.getenv("ALVEARE_DATA", "data/alveare")
        prefer = bool(os.getenv("CIVITAS_EMBED_MODEL"))
        emb = AlveareEmbedder(
            dim=int(os.getenv("ALVEARE_DIM", "384")),
            prefer_http=prefer,
        )
        STORE = AlveareStore(data, embedder=emb)
    return STORE


class Handler(BaseHTTPRequestHandler):
    server_version = "Alveare/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        return json.loads(raw.decode() or "{}")

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/health", "/ready"):
            st = get_store().stats()
            self._send(
                200,
                {"ok": True, "service": "alveare", "frozen": _frozen(), **st},
            )
            return
        self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._read_json()
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "invalid_json"})
            return
        store = get_store()
        if path == "/v1/query":
            tick_min = body.get("tick_min")
            tick_max = body.get("tick_max")
            hits = store.query(
                str(body.get("text") or ""),
                k=int(body.get("k") or 4),
                source=body.get("source"),
                tags=list(body.get("tags") or []) or None,
                agent_id=body.get("agent_id"),
                tick_min=int(tick_min) if tick_min is not None else None,
                tick_max=int(tick_max) if tick_max is not None else None,
            )
            self._send(200, {"ok": True, "hits": hits, "frozen": _frozen()})
            return
        if path in ("/v1/upsert", "/v1/ingest/markdown") and _frozen():
            self._send(423, {"ok": False, "error": "frozen_store", "frozen": True})
            return
        if path == "/v1/upsert":
            try:
                chunk = store.upsert(
                    str(body.get("text") or ""),
                    source=str(body.get("source") or "ops"),
                    tags=list(body.get("tags") or []),
                    agent_id=body.get("agent_id"),
                    tick=body.get("tick"),
                    id=body.get("id"),
                )
            except ValueError as exc:
                self._send(400, {"ok": False, "error": str(exc)})
                return
            self._send(200, {"ok": True, "chunk": chunk.public()})
            return
        if path == "/v1/ingest/markdown":
            vault = body.get("path") or os.getenv("ALVEARE_VAULT", "/vault")
            result = ingest_vault(
                store,
                vault,
                limit_files=body.get("limit_files"),
            )
            self._send(200, result)
            return
        self._send(404, {"ok": False, "error": "not_found"})


def main() -> None:
    host = os.getenv("ALVEARE_HOST", "127.0.0.1")
    port = int(os.getenv("ALVEARE_PORT", "9200"))
    get_store()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"[ALVEARE] listening on {host}:{port} data={os.getenv('ALVEARE_DATA', 'data/alveare')}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
