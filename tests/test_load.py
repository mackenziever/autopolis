"""Load test: suite rapida in CI + gate 1M tick via script dedicato."""
from __future__ import annotations

import asyncio
import os

import pytest

from config import SimConfig
from engine.tick_engine import CivitasEngine


def test_load_scaled_smoke(tmp_path):
    """Versione scalata per CI (~10k tick). Il gate 1M e' scripts/load_test.py."""
    ticks = int(os.getenv("CIVITAS_LOAD_TICKS", "10000"))
    cfg = SimConfig(
        num_agents=5,
        total_ticks=ticks,
        seed=42,
        log_path=str(tmp_path / "load.msgpack"),
        llm_record_path=str(tmp_path / "load.jsonl"),
        manifest_path=str(tmp_path / "load.manifest.json"),
        spatial_hash_enabled=True,
        delta_log_enabled=True,
        delta_keyframe_every=500,
        log_flush_every=500,
    )
    result = asyncio.run(CivitasEngine(cfg).run(realtime=False))
    assert result["ticks"] == ticks
    assert result["perf"]["log_bytes"] > 0
    assert "hits" in result["perf"]["path_cache"]


@pytest.mark.slow
def test_load_one_million_ticks(tmp_path):
    cfg = SimConfig(
        num_agents=5,
        total_ticks=1_000_000,
        seed=42,
        log_path=str(tmp_path / "load1m.msgpack"),
        llm_record_path=str(tmp_path / "load1m.jsonl"),
        manifest_path=str(tmp_path / "load1m.manifest.json"),
        spatial_hash_enabled=True,
        delta_log_enabled=True,
        delta_keyframe_every=2000,
        log_flush_every=2000,
    )
    result = asyncio.run(CivitasEngine(cfg).run(realtime=False))
    assert result["ticks"] == 1_000_000
    assert result["wall_hz"] > 0
