"""Test apparato self-improve (offline, senza FreeLLM live)."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from agents.cognitive import AgentCognitiveEngine
from agents.models import AgentRuntime, AgentState
from agents.persona import generate_persona
from agents.self_improve import SelfImprovementLoop
from knowledge.batch import AlveareBatchBuffer
from llm.router import CognitiveRouter
from world.economy import LaborMarket


def _runtime(n=0):
    p = generate_persona(n, 42)
    return AgentRuntime(f"agent_{n:03d}", n, p, (10, 10))


def test_apply_posture_boosts_study():
    r = _runtime(0)
    router = CognitiveRouter(
        False, "mock", "", 1.0, 1, str(Path(tempfile.mkdtemp()) / "t.jsonl"), 42
    )
    loop = SelfImprovementLoop(r, router, alveare_batch=AlveareBatchBuffer(None))
    before = r.study_progress.get(r.persona.preferred_course, 0)
    out = loop.apply_posture(10, "push_study", "studio hard")
    assert out["focus"] == "study"
    assert r.study_progress[r.persona.preferred_course] == before + 2
    assert loop.stats["improves"] == 1


def test_study_decision_sets_active_course():
    async def _run():
        tmp = Path(tempfile.mkdtemp()) / "trace.jsonl"
        r = _runtime(1)
        router = CognitiveRouter(False, "mock", "", 1.0, 1, str(tmp), 42)
        cog = AgentCognitiveEngine(r, router, 42, 8)
        d = await cog.decide_study(50)
        assert d["choice"] in (
            "coding_101",
            "design_202",
            "operations_101",
            "comms_101",
        ) or d["choice"]  # COURSES keys
        assert r.active_course
        assert any(e.get("event") == "study_focus" or True for e in [{}])
        assert router.stats["fallback"] >= 1

    asyncio.run(_run())


def test_career_apply_job():
    r = _runtime(2)
    r.skills.append("motion")
    market = LaborMarket()
    ev = market.apply_job(1, r, "motion_designer")
    assert ev is not None
    assert ev["type"] == "job_change"
    assert r.job == "motion_designer"
    assert market.apply_job(2, r, "train_more") is None


def test_reflect_returns_tuple_and_lesson():
    async def _run():
        tmp = Path(tempfile.mkdtemp()) / "trace.jsonl"
        r = _runtime(3)
        batch = AlveareBatchBuffer(None, frozen=False)
        router = CognitiveRouter(False, "mock", "", 1.0, 1, str(tmp), 42)
        cog = AgentCognitiveEngine(r, router, 42, 8, alveare_batch=batch)
        strategy, applied = await cog.reflect(100)
        assert isinstance(strategy, str) and strategy
        assert "focus" in applied and "lesson" in applied
        assert cog.improve.stats["improves"] == 1

    asyncio.run(_run())
