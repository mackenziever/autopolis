"""Feed derivato non autorevole per UI live. Se il client e' lento, i frame si scartano.

Hardening: bind solo su loopback di default; envelope opzionale HMAC.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import urlparse

import msgpack


def _is_loopback_endpoint(endpoint: str) -> bool:
    u = urlparse(endpoint.replace("://*", "://0.0.0.0"))
    host = (u.hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


class TelemetryPublisher:
    def __init__(self, endpoint: str | None = None):
        self.socket = None
        self.sent = 0
        self.dropped = 0
        self.endpoint = endpoint
        self._hmac_key = os.getenv("CIVITAS_ZMQ_HMAC_KEY")
        if not endpoint:
            return
        allow_public = os.getenv("CIVITAS_ZMQ_ALLOW_PUBLIC", "0") == "1"
        if not allow_public and not _is_loopback_endpoint(endpoint):
            # Rifiuta bind pubblici accidentali (es. tcp://*:5556).
            self.socket = None
            self.dropped += 1
            return
        try:
            import zmq

            ctx = zmq.Context.instance()
            s = ctx.socket(zmq.PUB)
            s.setsockopt(zmq.SNDHWM, 2)
            s.setsockopt(zmq.LINGER, 0)
            s.bind(endpoint)
            self.socket = s
        except Exception:
            self.socket = None

    def publish(self, tick: int, snapshots: list[dict]):
        if self.socket is None:
            return
        try:
            import zmq

            body = {"tick": tick, "agents": snapshots}
            packed = msgpack.packb(body, use_bin_type=True)
            if self._hmac_key:
                sig = hmac.new(self._hmac_key.encode(), packed, hashlib.sha256).hexdigest()
                packed = msgpack.packb({"payload": packed, "hmac": sig}, use_bin_type=True)
            self.socket.send(packed, flags=zmq.NOBLOCK)
            self.sent += 1
        except Exception:
            self.dropped += 1

    def close(self):
        if self.socket is not None:
            self.socket.close(0)
