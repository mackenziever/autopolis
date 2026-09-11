"""Living City smoke with FreeLLM/AGI-OS: 4 agents, short max-ticks, prints LLM stats.

Movement stays LLM-free; router stats reflect cognitive calls only.

Usage (from release root):
  python scripts/smoke_living_llm.py
  python scripts/smoke_living_llm.py --hermes
  python scripts/smoke_living_llm.py --no-llm
  python scripts/smoke_living_llm.py --max-ticks 60 --port 9310

Exit codes:
  0 — completed and printed stats
  1 — run failed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _load_dotenv_llm() -> None:
    path = ROOT / ".env.llm"
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v


async def amain() -> int:
    _load_dotenv_llm()
    p = argparse.ArgumentParser(description="4-agent living LLM smoke (short ticks)")
    p.add_argument("--agents", type=int, default=4)
    p.add_argument("--max-ticks", type=int, default=90)
    p.add_argument("--hz", type=int, default=15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--port", type=int, default=9310)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-llm", action="store_true")
    p.add_argument(
        "--hermes",
        action="store_true",
        help="LLM diretto su Hermes :8081 (qwable-9b), bypass FreeLLM catalog",
    )
    p.add_argument("--log", default="data/smoke_living_llm.msgpack")
    a = p.parse_args()

    from config import SimConfig
    from engine.tick_engine import CivitasEngine
    from living_server.app import run_living

    if a.hermes:
        api_base = os.getenv("HERMES_V1") or "http://127.0.0.1:8081/v1"
        # Do not inherit CIVITAS_LLM_MODEL=auto from .env.llm
        model = os.getenv("HERMES_MODEL") or "qwable-9b"
        os.environ.setdefault("CIVITAS_LLM_API_KEY", os.getenv("CIVITAS_LLM_API_KEY") or "local")
    else:
        api_base = os.getenv("CIVITAS_LLM_API_BASE") or "http://127.0.0.1:3001/v1"
        model = os.getenv("CIVITAS_LLM_MODEL") or "auto"
    alveare = os.getenv("CIVITAS_ALVEARE_URL") or "http://127.0.0.1:9200"
    frozen = _env_truthy("CIVITAS_REPLAY") or _env_truthy("CIVITAS_ALVEARE_FROZEN")

    cfg = SimConfig(
        num_agents=a.agents,
        total_ticks=10**9,
        tick_rate_hz=a.hz,
        seed=a.seed,
        log_path=a.log,
        llm_enabled=not a.no_llm,
        llm_api_base=api_base,
        llm_model=model,
        alveare_url=alveare,
        alveare_frozen=frozen,
        metrics_enabled=False,
        spatial_hash_enabled=True,
        cognitive_worker=True,
        paperclip_city_enabled=False,
        living_mode=True,
        living_port=a.port,
        delta_log_enabled=False,
    )
    engine = CivitasEngine(cfg, live_endpoint=None)
    result = await run_living(
        engine,
        host=a.host,
        port=a.port,
        realtime=False,
        max_ticks=a.max_ticks,
    )
    llm = (result or {}).get("llm") or dict(engine.router.stats)
    print(
        json.dumps(
            {
                "ok": True,
                "agents": a.agents,
                "max_ticks": a.max_ticks,
                "ticks": (result or {}).get("ticks"),
                "wall_seconds": (result or {}).get("wall_seconds"),
                "llm_api_base": api_base,
                "llm_model": model,
                "llm": llm,
                "last_latency_ms": llm.get("last_latency_ms"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    try:
        return asyncio.run(amain())
    except Exception as exc:
        print(f"[fail] smoke_living_llm: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
