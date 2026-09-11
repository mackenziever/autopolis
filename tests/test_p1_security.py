import asyncio
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from config import SimConfig
from engine.tick_engine import CivitasEngine
from security.hmac_replay import ReplayIntegrityError, sign_file, verify_file
from security.pii import PIISanitizer
from telemetry.bus import TelemetryPublisher, _is_loopback_endpoint


def test_pii_redacts_email_and_phone():
    text = "Contatta mario.rossi@example.com al +39 02 1234 5678"
    out = PIISanitizer.sanitize_text(text)
    assert "example.com" not in out
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_PHONE]" in out


def test_hmac_sign_and_verify(tmp_path, monkeypatch):
    monkeypatch.setenv("CIVITAS_REPLAY_HMAC_KEY", "test-hmac-secret")
    path = tmp_path / "r.msgpack"
    path.write_bytes(b"civitas-replay-bytes")
    digest = sign_file(str(path))
    assert len(digest) == 64
    assert verify_file(str(path)) is True
    path.write_bytes(b"tampered")
    with pytest.raises(ReplayIntegrityError):
        verify_file(str(path))


def test_zmq_rejects_public_bind_by_default(monkeypatch):
    monkeypatch.delenv("CIVITAS_ZMQ_ALLOW_PUBLIC", raising=False)
    assert _is_loopback_endpoint("tcp://127.0.0.1:5556")
    assert not _is_loopback_endpoint("tcp://*:5556")
    pub = TelemetryPublisher("tcp://*:5556")
    assert pub.socket is None


def test_manifest_and_optional_hmac(tmp_path, monkeypatch):
    monkeypatch.setenv("CIVITAS_REPLAY_HMAC_KEY", "manifest-secret")
    log = tmp_path / "m.msgpack"
    man = tmp_path / "manifest.json"
    cfg = SimConfig(
        num_agents=8,
        total_ticks=12,
        seed=3,
        log_path=str(log),
        llm_record_path=str(tmp_path / "t.jsonl"),
        manifest_path=str(man),
        sign_replay=True,
        metrics_enabled=False,
    )
    result = asyncio.run(CivitasEngine(cfg).run(realtime=False))
    assert man.exists()
    data = json.loads(man.read_text(encoding="utf-8"))
    assert data["ticks_completed"] == 12
    assert data["log_sha256"]
    assert result["hmac"] and len(result["hmac"]) == 64
    assert verify_file(str(log)) is True


def test_health_ready_endpoint():
    from metrics.collector import MetricsCollector
    from metrics.server import MetricsServer

    c = MetricsCollector()
    srv = MetricsServer(port=0, collector=c, health_extra=lambda: {"fingerprint": "abc"}).start()
    try:
        raw = urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/ready", timeout=2).read()
        body = json.loads(raw.decode())
        assert body["ok"] is True and body["ready"] is True
        assert body["fingerprint"] == "abc"
        assert body["service"] == "civitas"
    finally:
        srv.stop()


def test_llm_gateway_requires_bearer(monkeypatch):
    from security.llm_gateway import GatewayHandler

    # minimal upstream echo
    class Echo(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(n)
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_port = upstream.server_address[1]
    monkeypatch.setenv("CIVITAS_GATEWAY_TOKEN", "secret-token")
    handler = type(
        "H",
        (GatewayHandler,),
        {
            "upstream": f"http://127.0.0.1:{up_port}/v1",
            "token": "secret-token",
        },
    )
    gw = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=gw.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{gw.server_address[1]}/v1/chat/completions",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(req, timeout=2)
        assert ei.value.code == 401
        req2 = urllib.request.Request(
            f"http://127.0.0.1:{gw.server_address[1]}/v1/chat/completions",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer secret-token",
            },
        )
        with urllib.request.urlopen(req2, timeout=2) as resp:
            assert json.loads(resp.read().decode())["ok"] is True
    finally:
        gw.shutdown()
        upstream.shutdown()
