import asyncio

import pytest

from config import SimConfig
from engine.checkpoint import CheckpointError, load
from engine.tick_engine import CivitasEngine
from telemetry.logger import iter_records


def cfg(tmp_path, name, ticks, interval=0):
    return SimConfig(
        num_agents=20,
        total_ticks=ticks,
        seed=77,
        log_path=str(tmp_path / (name + ".msgpack")),
        llm_record_path=str(tmp_path / (name + ".jsonl")),
        checkpoint_path=str(tmp_path / (name + ".checkpoint")),
        checkpoint_interval_ticks=interval,
    )


def snapshots(path):
    return [
        e
        for r in iter_records(path)
        if r.get("record") == "tick"
        for e in r["events"]
        if e["type"] == "snapshot"
    ]


def test_checkpoint_resume_matches_uninterrupted_final_state(tmp_path):
    full = cfg(tmp_path, "full", 120)
    asyncio.run(CivitasEngine(full).run(realtime=False))
    first = cfg(tmp_path, "part", 60, 60)
    asyncio.run(CivitasEngine(first).run(realtime=False))
    resumed = cfg(tmp_path, "resumed", 120)
    engine = CivitasEngine(resumed)
    assert engine.resume_from(first.checkpoint_path) == 60
    asyncio.run(engine.run(realtime=False))
    full_last = snapshots(full.log_path)[-20:]
    resumed_last = snapshots(resumed.log_path)[-20:]
    assert full_last == resumed_last


def test_checkpoint_corruption_detected(tmp_path):
    c = cfg(tmp_path, "part", 20, 20)
    asyncio.run(CivitasEngine(c).run(realtime=False))
    p = tmp_path / "part.checkpoint"
    raw = bytearray(p.read_bytes())
    raw[-1] ^= 0x01
    p.write_bytes(raw)
    with pytest.raises(CheckpointError):
        load(str(p), c.fingerprint())


def test_checkpoint_config_mismatch_rejected(tmp_path):
    c = cfg(tmp_path, "part", 20, 20)
    asyncio.run(CivitasEngine(c).run(realtime=False))
    with pytest.raises(CheckpointError, match="Fingerprint"):
        load(c.checkpoint_path, "wrong")
