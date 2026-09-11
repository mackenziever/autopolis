"""Test EscalationGate (isteresi + cooldown, Tier 0 -> Tier 1)."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from agents.escalation import EscalationGate
from llm.router import CognitiveRouter


def test_no_escalation_below_enter_threshold():
    gate = EscalationGate(enter_threshold=0.5, exit_threshold=0.2, cooldown_cycles=2)
    for _ in range(5):
        assert gate.decide(0.3) is False


def test_escalates_once_signal_crosses_enter_threshold():
    gate = EscalationGate(enter_threshold=0.5, exit_threshold=0.2, cooldown_cycles=2)
    assert gate.decide(0.6) is True


def test_cooldown_forces_tier0_after_escalation():
    gate = EscalationGate(enter_threshold=0.5, exit_threshold=0.2, cooldown_cycles=2)
    assert gate.decide(0.9) is True
    gate.note_cycle_result(escalated=True)
    # cooldown: anche con segnale altissimo, i prossimi 2 cicli restano Tier 0
    assert gate.decide(0.9) is False
    assert gate.decide(0.9) is False
    # cooldown esaurito: ora puo' riattivarsi
    assert gate.decide(0.9) is True


def test_hysteresis_stays_active_between_thresholds():
    gate = EscalationGate(enter_threshold=0.5, exit_threshold=0.2, cooldown_cycles=0)
    assert gate.decide(0.6) is True
    gate.note_cycle_result(escalated=True)
    # segnale sceso ma ancora sopra exit_threshold -> resta attivo (isteresi)
    assert gate.decide(0.3) is True
    gate.note_cycle_result(escalated=True)
    # sotto exit_threshold -> disattiva
    assert gate.decide(0.1) is False


def test_state_round_trip():
    gate = EscalationGate(cooldown_cycles=3)
    gate.decide(0.9)
    gate.note_cycle_result(escalated=True)
    state = gate.to_state()

    restored = EscalationGate(cooldown_cycles=3)
    restored.load_state(state)
    assert restored.decide(0.9) == gate.decide(0.9)


def test_router_escalate_false_skips_live_call_even_when_enabled():
    """escalate=False deve forzare Tier 0 (fallback) anche con self.enabled=True,
    senza mai tentare il transport live, e contare tier0_skipped_escalation."""
    calls = {"n": 0}

    async def _never_call_transport(**kwargs):
        calls["n"] += 1
        return {"content": '{"choice": "consolidate_skills", "thought": "x", "confidence": 0.9}'}

    router = CognitiveRouter(
        True,
        "mock",
        "",
        1.0,
        1,
        str(Path(tempfile.mkdtemp()) / "t.jsonl"),
        42,
        transport=_never_call_transport,
    )
    d = asyncio.run(
        router.decide(
            agent_id="agent_000",
            tick=0,
            event="daily_reflection",
            choices=["consolidate_skills", "recover_energy"],
            system_prompt="test",
            context={},
            escalate=False,
        )
    )
    assert calls["n"] == 0
    assert router.stats["tier0_skipped_escalation"] == 1
    assert router.stats["live"] == 0
    assert d.choice in ("consolidate_skills", "recover_energy")
    assert d.source == "fallback"


def test_router_escalate_true_default_calls_transport_when_enabled():
    calls = {"n": 0}

    async def _mock_transport(**kwargs):
        calls["n"] += 1
        return {"content": '{"choice": "recover_energy", "thought": "x", "confidence": 0.9}'}

    router = CognitiveRouter(
        True,
        "mock",
        "",
        1.0,
        1,
        str(Path(tempfile.mkdtemp()) / "t.jsonl"),
        42,
        transport=_mock_transport,
    )
    d = asyncio.run(
        router.decide(
            agent_id="agent_000",
            tick=0,
            event="daily_reflection",
            choices=["consolidate_skills", "recover_energy"],
            system_prompt="test",
            context={},
        )
    )
    assert calls["n"] == 1
    assert router.stats["live"] == 1
    assert router.stats["tier0_skipped_escalation"] == 0
    assert d.source == "live"


def test_router_cache_replay_preserves_original_source():
    """Bugfix determinismo (2026-09-11): `Decision.source` va fissato alla PRIMA
    scrittura nel trace e deve restare identico su ogni replay successivo, anche in
    un router "fresco" (nuovo processo) che legge lo stesso file di trace — a
    differenza dei vecchi contatori globali router.stats["live"]/["replay"], che
    agents/cognitive.py.reflect() usava per dedurre se un d.thought fosse "reale":
    quei contatori dipendono da COSA ALTRO e' gia' successo su quel router/processo,
    non dalla singola decisione, ed erano la causa di un mismatch di replay fra due
    run altrimenti identiche."""
    trace_path = str(Path(tempfile.mkdtemp()) / "t.jsonl")

    async def _mock_live(**kwargs):
        return {"content": '{"choice": "recover_energy", "thought": "reale", "confidence": 0.9}'}

    router_a = CognitiveRouter(True, "mock", "", 1.0, 1, trace_path, 42, transport=_mock_live)
    d1 = asyncio.run(
        router_a.decide(
            agent_id="agent_000", tick=0, event="daily_reflection",
            choices=["consolidate_skills", "recover_energy"],
            system_prompt="test", context={},
        )
    )
    assert d1.source == "live"

    async def _never_call(**kwargs):
        raise AssertionError("non deve chiamare il transport: rid gia' in cache")

    router_b = CognitiveRouter(True, "mock", "", 1.0, 1, trace_path, 42, transport=_never_call)
    d2 = asyncio.run(
        router_b.decide(
            agent_id="agent_000", tick=0, event="daily_reflection",
            choices=["consolidate_skills", "recover_energy"],
            system_prompt="test", context={},
        )
    )
    assert router_b.stats["replay"] == 1
    assert d2.source == "live"  # ereditato dalla cache, non "unknown" ne' "fallback"
    assert d2.choice == d1.choice
    assert d2.thought == d1.thought
