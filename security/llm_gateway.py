"""Gateway locale TLS/Auth + rate-limit davanti a un upstream compatibile con il formato chat-completion standard.

Uso tipico:
  python -m security.llm_gateway --listen 127.0.0.1:8443 \\
    --upstream http://127.0.0.1:8000/v1 --token-env CIVITAS_GATEWAY_TOKEN

Il simulatore punta --llm a https://127.0.0.1:8443/v1 (o http se senza cert).
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple

from security.hardening import RateLimitExceeded, SecretManager, TokenBucket


def _parse_host_port(value: str) -> Tuple[str, int]:
    host, _, port = value.rpartition(":")
    return host or "127.0.0.1", int(port or "8443")


class GatewayHandler(BaseHTTPRequestHandler):
    upstream: str = "http://127.0.0.1:8000/v1"
    token: str | None = None
    bucket: TokenBucket = TokenBucket(rate_per_s=5.0, capacity=10.0)
    secrets: SecretManager = SecretManager(("CIVITAS_GATEWAY_TOKEN", "CIVITAS_LLM_API_KEY"))

    def _client_key(self) -> str:
        return self.client_address[0]

    def _unauthorized(self, msg: str = "unauthorized"):
        body = json.dumps({"error": msg}).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        if not self.token:
            return True
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {self.token}":
            return True
        self._unauthorized()
        return False

    def _check_rate(self) -> bool:
        try:
            self.bucket.require(self._client_key())
            return True
        except RateLimitExceeded:
            body = b'{"error":"rate_limited"}'
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return False

    def do_GET(self):
        if self.path.split("?", 1)[0] in ("/health", "/v1/health"):
            body = json.dumps({"ok": True, "upstream": self.upstream, "auth": bool(self.token)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if not self._check_auth() or not self._check_rate():
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        target = self.upstream.rstrip("/") + self.path
        if not self.path.startswith("/"):
            target = self.upstream.rstrip("/") + "/" + self.path
        # Normalize: client often posts to /v1/chat/completions while upstream already includes /v1
        if self.path.startswith("/v1/") and self.upstream.rstrip("/").endswith("/v1"):
            target = self.upstream.rstrip("/") + self.path[3:]
        req = urllib.request.Request(
            target,
            data=raw,
            method="POST",
            headers={
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Authorization": self.headers.get("Authorization", ""),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:
            payload = json.dumps({"error": self.secrets.mask(str(exc))}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Civitas LLM TLS/Auth gateway")
    p.add_argument("--listen", default="127.0.0.1:8443")
    p.add_argument("--upstream", default="http://127.0.0.1:8000/v1")
    p.add_argument("--token-env", default="CIVITAS_GATEWAY_TOKEN")
    p.add_argument("--rate", type=float, default=5.0, help="req/s per client IP")
    p.add_argument("--burst", type=float, default=10.0)
    p.add_argument("--cert", default=None, help="PEM cert for TLS")
    p.add_argument("--key", default=None, help="PEM key for TLS")
    a = p.parse_args(argv)
    host, port = _parse_host_port(a.listen)
    token = os.getenv(a.token_env) or None
    handler = type(
        "BoundGateway",
        (GatewayHandler,),
        {
            "upstream": a.upstream,
            "token": token,
            "bucket": TokenBucket(a.rate, a.burst),
        },
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    if a.cert and a.key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=a.cert, keyfile=a.key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        print(f"[GATEWAY] TLS https://{host}:{port} -> {a.upstream} auth={bool(token)}")
    else:
        print(f"[GATEWAY] http://{host}:{port} -> {a.upstream} auth={bool(token)}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
