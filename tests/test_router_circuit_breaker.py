"""Circuit breaker + retry nel router LLM (consiglio esterno, 2026-09-11,
"3. Circuit breaker + fallback semantico"): freellmapi e' un'immagine Docker
di terze parti free-tier, la resilienza va sul lato client (CognitiveRouter)."""
from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

from llm.router import CognitiveRouter


def _new_router(transport, *, threshold=3, open_seconds=30.0, max_retries=0):
    router = CognitiveRouter(
        True,
        "mock",
        "",
        1.0,
        1,
        str(Path(tempfile.mkdtemp()) / "t.jsonl"),
        42,
        transport=transport,
    )
    router.CB_FAILURE_THRESHOLD = threshold
    router.CB_OPEN_SECONDS = open_seconds
    router.CB_MAX_RETRIES = max_retries
    return router


def _decide(router, tick):
    return asyncio.run(
        router.decide(
            agent_id="agent_000",
            tick=tick,
            event="daily_reflection",
            choices=["consolidate_skills", "recover_energy"],
            system_prompt="test",
            context={},
        )
    )


def test_breaker_opens_after_threshold_failures_and_skips_transport():
    calls = {"n": 0}

    async def _always_fail(**kwargs):
        calls["n"] += 1
        raise RuntimeError("provider down")

    router = _new_router(_always_fail, threshold=3, max_retries=0)
    for tick in range(3):
        d = _decide(router, tick)
        assert d.source == "fallback"
    assert calls["n"] == 3
    assert router.stats["circuit_breaker_trips"] == 1

    # Breaker aperto: la prossima decisione NON deve toccare il transport.
    d = _decide(router, 999)
    assert d.source == "fallback"
    assert calls["n"] == 3  # invariato
    assert router.stats["circuit_breaker_skipped"] == 1


def test_breaker_resets_on_success_after_partial_failures():
    calls = {"n": 0}

    async def _fail_then_succeed(**kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("provider flaky")
        return {"content": '{"choice": "recover_energy", "thought": "ok", "confidence": 0.9}'}

    router = _new_router(_fail_then_succeed, threshold=3, max_retries=0)
    _decide(router, 0)
    _decide(router, 1)
    assert router._cb_failures == 2
    d = _decide(router, 2)
    assert d.source == "live"
    assert router._cb_failures == 0
    assert router.stats["circuit_breaker_trips"] == 0


def test_breaker_closes_again_after_open_seconds_elapsed():
    async def _always_fail(**kwargs):
        raise RuntimeError("provider down")

    router = _new_router(_always_fail, threshold=1, open_seconds=0.05, max_retries=0)
    _decide(router, 0)
    assert router.stats["circuit_breaker_trips"] == 1
    time.sleep(0.1)
    # Trascorso CB_OPEN_SECONDS, il prossimo tentativo riprova il transport
    # (e fallisce di nuovo, riaprendo il breaker) invece di restare bloccato.
    _decide(router, 1)
    assert router.stats["circuit_breaker_skipped"] == 0


def test_retries_before_tripping_breaker():
    calls = {"n": 0}

    async def _always_fail(**kwargs):
        calls["n"] += 1
        raise RuntimeError("provider down")

    router = _new_router(_always_fail, threshold=1, max_retries=2)
    _decide(router, 0)
    assert calls["n"] == 3  # 1 tentativo + 2 retry
    assert router.stats["retries"] == 2
    assert router.stats["circuit_breaker_trips"] == 1
