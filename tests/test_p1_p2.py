import asyncio
import urllib.request

import pytest

from config import SimConfig
from engine.spatial_hash import SpatialHashGrid
from engine.spatial import SpatialService
from engine.tick_engine import CivitasEngine
from metrics.collector import MetricsCollector
from metrics.server import MetricsServer
from security.hardening import InputValidator, SecretManager, TokenBucket, ValidationError
from telemetry.delta_logger import DeltaTelemetryLogger, expand_records
from world.map import CityMap


def test_metrics_server_health_and_prometheus():
    c = MetricsCollector()
    c.inc("civitas_ticks_total")
    c.observe("civitas_tick_seconds", 0.01)
    srv = MetricsServer(port=0, collector=c).start()
    try:
        health = urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/health", timeout=2).read()
        assert b'"ok": true' in health or b'"ok":true' in health
        body = urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/metrics", timeout=2).read().decode()
        assert "civitas_ticks_total" in body
        assert "civitas_uptime_seconds" in body
    finally:
        srv.stop()


def test_security_validator_and_secrets(monkeypatch):
    assert InputValidator.agent_id("agent_001") == "agent_001"
    with pytest.raises(ValidationError):
        InputValidator.agent_id("../evil")
    with pytest.raises(ValidationError):
        InputValidator.path("/abs/secret")
    assert "\x00" not in InputValidator.sanitize_prompt("hi\x00there")
    monkeypatch.setenv("CIVITAS_LLM_API_KEY", "super-secret-token")
    sm = SecretManager()
    assert "***REDACTED***" in sm.mask("Bearer super-secret-token")
    bucket = TokenBucket(rate_per_s=100, capacity=1)
    assert bucket.allow("a")
    assert not bucket.allow("a")


def test_spatial_hash_matches_bruteforce_pairs():
    m = CityMap(64, 64, 42, 0.08)
    spatial = SpatialService(m)
    grid = SpatialHashGrid(4.0)
    positions = {f"agent_{i:03d}": (i % 20, i // 20) for i in range(40)}
    a = spatial.all_pairs_near(positions, 4.0)
    b = grid.all_pairs_near(positions, 4.0)
    assert a == b


def test_delta_logger_compression_and_expand(tmp_path):
    path = tmp_path / "d.msgpack"
    log = DeltaTelemetryLogger(str(path), {"test": True}, flush_every=1, keyframe_every=2)
    for t in range(6):
        events = [
            {
                "type": "snapshot",
                "agent_id": "agent_001",
                "tick": t,
                "name": "A",
                "x": t,
                "y": 0,
                "state": "WORKING",
                "target": "Office",
                "energy": 90 - t,
                "hunger": t,
                "money": 10,
                "job": "intern",
                "skills": ["basic_literacy"],
                "thought": "ok",
            }
        ]
        log.log_tick(t, float(t), events)
    log.close()
    assert log.stats["keyframes"] >= 1
    assert log.stats["delta_events"] >= 1
    assert log.compression_ratio() >= 1.0
    snaps = [
        e
        for r in expand_records(str(path))
        if r.get("record") == "tick"
        for e in r["events"]
        if e["type"] == "snapshot"
    ]
    assert snaps[-1]["x"] == 5
    assert snaps[-1]["energy"] == 85


def test_p1_p2_engine_integration(tmp_path):
    cfg = SimConfig(
        num_agents=15,
        total_ticks=40,
        seed=9,
        log_path=str(tmp_path / "run.msgpack"),
        llm_record_path=str(tmp_path / "t.jsonl"),
        spatial_hash_enabled=True,
        delta_log_enabled=True,
        delta_keyframe_every=10,
        metrics_enabled=True,
        metrics_port=0,
    )
    result = asyncio.run(CivitasEngine(cfg).run(realtime=False))
    assert result["ticks"] == 40
    assert result["spatial_hash"] is True
    assert result["delta_log"]["keyframes"] >= 1
    assert (tmp_path / "run.msgpack").exists()
