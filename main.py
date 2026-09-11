from __future__ import annotations

import argparse
import asyncio
import os

from config import SimConfig
from engine.tick_engine import CivitasEngine


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def args():
    p = argparse.ArgumentParser(description="Civitas: simulatore urbano deterministico headless")
    p.add_argument("--agents", type=int, default=50)
    p.add_argument("--ticks", type=int, default=600)
    p.add_argument("--hz", type=int, default=15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--log", default="data/simulation_replay.msgpack")
    p.add_argument(
        "--llm-trace",
        default="data/llm_trace.jsonl",
        help=(
            "path del trace cache LLM (request-hash -> response). Attenzione: e' lo "
            "STESSO file usato dal servizio 'living' in Docker (docker-compose.yml "
            "monta ./data:/app/data) - per run isolate/determinismo one-off, punta a "
            "un path separato (es. /tmp/t.jsonl) per non sovrascrivere la cache "
            "accumulata dalla citta' persistente."
        ),
    )
    p.add_argument("--fast", action="store_true", help="benchmark: non attendere il tempo reale")
    p.add_argument("--llm", action="store_true", help="abilita LiteLLM / FreeLLMAPI / Hermes")
    p.add_argument(
        "--llm-api-base",
        default=None,
        help="compatibile con il formato chat-completion standard base (default env CIVITAS_LLM_API_BASE o Hermes :8081)",
    )
    p.add_argument(
        "--llm-model",
        default=None,
        help="model id (default env CIVITAS_LLM_MODEL o config)",
    )
    p.add_argument(
        "--alveare-url",
        default=None,
        help="Alveare RAG URL (default env CIVITAS_ALVEARE_URL)",
    )
    p.add_argument("--live", default=None, help="endpoint ZMQ PUB es. tcp://*:5556")
    p.add_argument("--checkpoint", default="data/simulation.checkpoint.msgpack")
    p.add_argument(
        "--checkpoint-every",
        type=int,
        default=0,
        help="checkpoint atomico ogni N tick; 0=off",
    )
    p.add_argument(
        "--resume",
        default=None,
        help="riprendi da un checkpoint; --ticks indica il tick finale",
    )
    p.add_argument("--metrics", action="store_true", help="avvia /metrics e /health")
    p.add_argument("--metrics-port", type=int, default=9100)
    p.add_argument("--spatial-hash", action="store_true", help="usa SpatialHashGrid per proximity")
    p.add_argument(
        "--spatial-backend",
        choices=("python", "rust"),
        default="python",
        help="backend spatial (rust richiede modulo civitas_spatial)",
    )
    p.add_argument(
        "--cognitive-worker",
        action="store_true",
        help="avvia worker cognitivo async fuori dal hot-path movimento",
    )
    p.add_argument("--delta-log", action="store_true", help="keyframe+delta nel registro")
    p.add_argument("--keyframe-every", type=int, default=60)
    p.add_argument("--manifest", default="data/run_manifest.json")
    p.add_argument("--sign-replay", action="store_true", help="firma HMAC sidecar del replay")
    p.add_argument("--otel", action="store_true", help="export span OTel-lite")
    p.add_argument(
        "--paperclip-city",
        action="store_true",
        help="abilita Paperclip-city: task board locale per reflect/career/study/social",
    )
    p.add_argument(
        "--web-search",
        action="store_true",
        help="abilita ricerca internet reale nel research loop (fuori hot-path, cache per replay)",
    )
    p.add_argument(
        "--no-mayor",
        action="store_true",
        help=(
            "disabilita il sindaco (agents/mayor.py, provider LLM cloud "
            "separato) anche se configurato nell'ambiente — utile per "
            "audit/test ripetuti che non devono consumare budget a pagamento"
        ),
    )
    p.add_argument(
        "--web-search-trace",
        default="data/web_search_trace.jsonl",
        help="path del trace cache ricerca web — stesso avvertimento di --llm-trace",
    )
    return p.parse_args()


async def amain():
    a = args()
    api_base = (
        a.llm_api_base
        or os.getenv("CIVITAS_LLM_API_BASE")
        or "http://127.0.0.1:8081/v1"
    )
    model = a.llm_model or os.getenv("CIVITAS_LLM_MODEL") or "qwable-9b"
    alveare_url = a.alveare_url or os.getenv("CIVITAS_ALVEARE_URL") or ""
    frozen = _env_truthy("CIVITAS_REPLAY") or _env_truthy("CIVITAS_ALVEARE_FROZEN")
    cfg = SimConfig(
        num_agents=a.agents,
        total_ticks=a.ticks,
        tick_rate_hz=a.hz,
        seed=a.seed,
        log_path=a.log,
        llm_record_path=a.llm_trace,
        llm_enabled=a.llm,
        llm_api_base=api_base,
        llm_model=model,
        alveare_url=alveare_url,
        alveare_frozen=frozen,
        checkpoint_path=a.checkpoint,
        checkpoint_interval_ticks=a.checkpoint_every,
        metrics_enabled=a.metrics,
        metrics_port=a.metrics_port,
        spatial_hash_enabled=a.spatial_hash,
        spatial_backend=a.spatial_backend,
        cognitive_worker=a.cognitive_worker,
        delta_log_enabled=a.delta_log,
        delta_keyframe_every=a.keyframe_every,
        manifest_path=a.manifest,
        sign_replay=a.sign_replay,
        otel_enabled=a.otel,
        paperclip_city_enabled=a.paperclip_city,
        web_search_enabled=a.web_search,
        web_search_trace_path=a.web_search_trace,
        mayor_enabled=not a.no_mayor,
    )
    engine = CivitasEngine(cfg, a.live)
    if a.resume:
        start = engine.resume_from(a.resume)
        print(f"[RECOVERY] ripresa dal tick {start}")
    return await engine.run(realtime=not a.fast)


if __name__ == "__main__":
    try:
        import uvloop

        uvloop.run(amain())
    except ImportError:
        asyncio.run(amain())
