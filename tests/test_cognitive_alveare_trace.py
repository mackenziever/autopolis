"""Retrieval Alveare: chunk completi nel LLMTrace per replay indipendente dallo store."""
from __future__ import annotations

import asyncio
from pathlib import Path

from agents.cognitive import AgentCognitiveEngine
from agents.models import AgentRuntime
from agents.persona import generate_persona
from knowledge.batch import AlveareBatchBuffer
from llm.router import CognitiveRouter


class FakeAlveare:
    def __init__(self, hits):
        self.hits = hits
        self.queries = 0

    def query(self, text, k=4, source=None, **kwargs):
        self.queries += 1
        return self.hits


def test_retrieval_chunks_traced_and_replayed(tmp_path):
    trace = tmp_path / "llm.jsonl"
    router = CognitiveRouter(
        enabled=False,
        model="mock",
        api_base="http://127.0.0.1:9/v1",
        timeout_s=1,
        max_concurrency=1,
        trace_path=str(trace),
        seed=42,
    )
    hits = [
        {
            "id": "abc",
            "source": "vault",
            "text": "Regola condivisa: studia al mattino.",
            "score": 0.9,
            "tags": ["vault"],
        }
    ]
    fake = FakeAlveare(hits)
    batch = AlveareBatchBuffer(None, frozen=False)
    persona = generate_persona(0, 42)
    rt = AgentRuntime("agent_000", 0, persona, (6, 6))
    cog = AgentCognitiveEngine(
        rt, router, 42, 384, alveare=fake, alveare_batch=batch
    )

    async def _run():
        await cog.reflect(599)
        q1 = fake.queries
        await cog.reflect(599)
        return q1, fake.queries

    q1, q2 = asyncio.run(_run())
    assert q1 == 1
    assert q2 == 1  # secondo reflect riusa trace, non lo store
    raw = Path(trace).read_text(encoding="utf-8")
    assert "Regola condivisa: studia al mattino." in raw
    assert "alveare_retrieval" in raw
