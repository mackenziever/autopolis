"""CLI: python -m living_server --agents 12"""
from __future__ import annotations

import argparse
import asyncio
import os

from config import SimConfig
from engine.tick_engine import CivitasEngine
from living_server.app import run_living


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _load_dotenv_llm():
    path = os.path.join(os.path.dirname(__file__), "..", ".env.llm")
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Civitas Living City AGI-OS server")
    p.add_argument("--agents", type=int, default=12)
    p.add_argument("--hz", type=int, default=15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--port", type=int, default=int(os.getenv("LIVING_PORT", "9300")))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--fast", action="store_true", help="non attendere wall-clock")
    p.add_argument("--max-ticks", type=int, default=0, help="0=infinito; smoke: 120")
    p.add_argument("--no-llm", action="store_true")
    p.add_argument(
        "--hermes",
        action="store_true",
        help="LLM diretto su Hermes :8081 (qwable-9b) bypass FreeLLM catalog",
    )
    p.add_argument(
        "--web-search",
        action="store_true",
        help="Forza ricerca internet (DuckDuckGo/Wikipedia) nel research loop",
    )
    p.add_argument(
        "--no-web-search",
        action="store_true",
        help="Disabilita ricerca internet (default living: abilitata se non replay)",
    )
    p.add_argument("--log", default="data/living_replay.msgpack")
    p.add_argument(
        "--checkpoint",
        default="data/living.checkpoint.msgpack",
        help="Salva/riprende stato agenti qui ad ogni confine di giorno + shutdown. "
        "Vuoto ('') per disabilitare (nessuna persistenza tra restart).",
    )
    return p


async def amain():
    _load_dotenv_llm()
    a = build_parser().parse_args()
    if a.hermes:
        api_base = os.getenv("HERMES_V1") or "http://127.0.0.1:8081/v1"
        # Prefer HERMES_MODEL; ignore CIVITAS_LLM_MODEL=auto from .env.llm
        model = os.getenv("HERMES_MODEL") or "qwable-9b"
        os.environ.setdefault("CIVITAS_LLM_API_KEY", os.getenv("CIVITAS_LLM_API_KEY") or "local")
    else:
        api_base = os.getenv("CIVITAS_LLM_API_BASE") or "http://127.0.0.1:3001/v1"
        model = os.getenv("CIVITAS_LLM_MODEL") or "auto"
    alveare = os.getenv("CIVITAS_ALVEARE_URL") or "http://127.0.0.1:9200"
    frozen = _env_truthy("CIVITAS_REPLAY") or _env_truthy("CIVITAS_ALVEARE_FROZEN")
    # Living City: web explore ON di default (cittadini → vault/Alveare → self-improve).
    # Off se replay/frozen, --no-web-search, o CIVITAS_WEB_SEARCH=0.
    env_web = os.getenv("CIVITAS_WEB_SEARCH", "").strip().lower()
    if a.no_web_search or frozen or env_web in ("0", "false", "no", "off"):
        web_on = False
    elif a.web_search or env_web in ("1", "true", "yes", "on") or env_web == "":
        web_on = True
    else:
        web_on = False
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
        metrics_enabled=True,
        metrics_port=9102,
        spatial_hash_enabled=True,
        cognitive_worker=True,
        paperclip_city_enabled=True,
        living_mode=True,
        living_port=a.port,
        delta_log_enabled=True,
        web_search_enabled=web_on,
        city_growth_enabled=True,
        construction_enabled=True,
    )
    engine = CivitasEngine(cfg, live_endpoint=None)
    if a.checkpoint and os.path.isfile(a.checkpoint):
        try:
            start = engine.resume_from(a.checkpoint)
            print(f"[LIVING] resumed from checkpoint tick={start}")
        except Exception as exc:
            print(f"[LIVING] checkpoint resume failed ({exc}); starting fresh")
    max_ticks = a.max_ticks or None
    result = await run_living(
        engine,
        host=a.host,
        port=a.port,
        realtime=not a.fast,
        max_ticks=max_ticks,
        checkpoint_path=a.checkpoint or None,
    )
    print("[LIVING]", result)


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
