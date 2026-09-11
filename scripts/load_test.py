#!/usr/bin/env python3
"""Load test multi-giorno: target >= 1_000_000 tick headless.

Esempio:
  python scripts/load_test.py --ticks 1000000 --agents 5 --spatial-hash
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import SimConfig
from engine.tick_engine import CivitasEngine


def main() -> int:
    p = argparse.ArgumentParser(description="Civitas load test >= 1M ticks")
    p.add_argument("--agents", type=int, default=5)
    p.add_argument("--ticks", type=int, default=1_000_000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--spatial-hash", action="store_true", default=True)
    p.add_argument("--no-spatial-hash", action="store_false", dest="spatial_hash")
    p.add_argument(
        "--spatial-backend",
        choices=("python", "rust"),
        default="python",
    )
    p.add_argument("--delta-log", action="store_true", default=True)
    p.add_argument("--log", default="data/load_test.msgpack")
    p.add_argument("--min-ticks", type=int, default=1_000_000, help="soglia PASS")
    a = p.parse_args()
    cfg = SimConfig(
        num_agents=a.agents,
        total_ticks=a.ticks,
        seed=a.seed,
        log_path=a.log,
        llm_record_path=str(Path(a.log).with_suffix(".jsonl")),
        spatial_hash_enabled=a.spatial_hash,
        spatial_backend=a.spatial_backend,
        delta_log_enabled=a.delta_log,
        delta_keyframe_every=600,
        log_flush_every=600,
        manifest_path=str(Path(a.log).with_suffix(".manifest.json")),
    )
    result = asyncio.run(CivitasEngine(cfg).run(realtime=False))
    ok = result.get("ticks", 0) >= a.min_ticks
    out = {
        "ok": ok,
        "required_ticks": a.min_ticks,
        "agents": a.agents,
        "result": result,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
