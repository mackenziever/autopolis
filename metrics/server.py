"""HTTP server minimale per /metrics, /health, /ready con rate-limit."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

from metrics.collector import GLOBAL_COLLECTOR, MetricsCollector
from security.hardening import TokenBucket


class _Handler(BaseHTTPRequestHandler):
    collector: MetricsCollector = GLOBAL_COLLECTOR
    bucket: TokenBucket = TokenBucket(rate_per_s=20.0, capacity=40.0)
    health_extra: Callable[[], dict] | None = None
    started_at: float = time.time()

    def _rate_ok(self) -> bool:
        if self.bucket.allow(self.client_address[0]):
            return True
        body = b'{"ok":false,"error":"rate_limited"}'
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def do_GET(self):
        if not self._rate_ok():
            return
        path = self.path.split("?", 1)[0]
        if path == "/metrics":
            body = self.collector.render_prometheus().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/health", "/ready"):
            payload = {
                **self.collector.health(),
                "ready": True,
                "uptime_s": round(time.time() - self.started_at, 3),
                "service": "civitas",
            }
            if self.health_extra:
                try:
                    extra = self.health_extra() or {}
                    payload.update(extra)
                    payload["ready"] = bool(payload.get("ready", True))
                except Exception as exc:
                    payload["ready"] = False
                    payload["health_error"] = str(exc)
            payload["ok"] = bool(payload.get("ok", True))
            code = 200 if payload["ok"] and payload["ready"] else 503
            raw = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_):
        return


class MetricsServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9100,
        collector: MetricsCollector | None = None,
        health_extra: Callable[[], dict] | None = None,
        rate_per_s: float = 20.0,
    ):
        self.host, self.port = host, port
        self.collector = collector or GLOBAL_COLLECTOR
        self.health_extra = health_extra
        self.rate_per_s = rate_per_s
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "MetricsServer":
        extra = self.health_extra or (lambda: {})
        handler = type(
            "BoundHandler",
            (_Handler,),
            {
                "collector": self.collector,
                "bucket": TokenBucket(self.rate_per_s, self.rate_per_s * 2),
                "health_extra": staticmethod(extra),
                "started_at": time.time(),
            },
        )
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
