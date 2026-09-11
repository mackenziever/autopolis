import asyncio
import json

from llm.router import CognitiveRouter


class MockTransport:
    def __init__(self):
        self.calls = 0

    async def __call__(self, *, messages, **kwargs):
        self.calls += 1
        return {
            "content": json.dumps(
                {"choice": "work", "thought": "Decisione mock.", "confidence": 0.9}
            ),
            "input_tokens": 21,
            "output_tokens": 7,
        }


def make(path, transport, **kw):
    opts = dict(
        day_length=100,
        max_output_tokens=16,
        requests_per_agent=3,
        input_per_agent=1000,
        output_per_agent=1000,
        global_requests=20,
        global_input=10000,
        global_output=10000,
    )
    opts.update(kw)
    return CognitiveRouter(
        True, "mock/model", "http://mock/v1", 1, 2, str(path), 42, transport=transport, **opts
    )


def request(r, tick=0):
    return asyncio.run(
        r.decide(
            agent_id="agent_001",
            tick=tick,
            event="choose_job",
            choices=["work", "rest"],
            system_prompt="JSON",
            context={"energy": 90},
        )
    )


def test_live_then_trace_replay_without_second_transport_call(tmp_path):
    trace = tmp_path / "trace.jsonl"
    m1 = MockTransport()
    r1 = make(trace, m1)
    d1 = request(r1)
    assert d1.choice == "work" and m1.calls == 1 and r1.stats["live"] == 1

    class MustNotRun:
        async def __call__(self, **kwargs):
            raise AssertionError("transport called during replay")

    r2 = make(trace, MustNotRun())
    d2 = request(r2)
    assert d2 == d1 and r2.stats["replay"] == 1


def test_budget_denies_after_limit(tmp_path):
    m = MockTransport()
    r = make(tmp_path / "trace.jsonl", m, requests_per_agent=1)
    request(r, tick=0)
    d = asyncio.run(
        r.decide(
            agent_id="agent_001",
            tick=1,
            event="choose_job",
            choices=["work", "rest"],
            system_prompt="JSON",
            context={"energy": 80},
        )
    )
    assert m.calls == 1 and r.stats["budget_denied"] == 1
    assert "budget:" in d.thought


def test_invalid_live_output_falls_back_and_is_traced(tmp_path):
    class Invalid:
        async def __call__(self, **kwargs):
            return {"content": "not json", "input_tokens": 1, "output_tokens": 1}

    trace = tmp_path / "trace.jsonl"
    r = make(trace, Invalid())
    d = request(r)
    assert d.choice in ("work", "rest") and r.stats["errors"] == 1 and r.stats["fallback"] == 1
    assert trace.exists() and len(trace.read_text(encoding="utf-8").splitlines()) == 1


def test_rid_populated_on_live_replay_and_fallback(tmp_path):
    """Approfondimento RSI (2026-09-11): Decision.rid deve essere lo stesso
    request id in tutti e 3 i percorsi — live, replay dal trace, fallback —
    cosi' un chiamante puo' sempre risalire alla richiesta esatta."""
    trace = tmp_path / "trace.jsonl"
    m1 = MockTransport()
    r1 = make(trace, m1)
    d_live = request(r1)
    assert d_live.rid  # non vuoto

    r2 = make(trace, MockTransport())
    d_replay = request(r2)
    assert d_replay.rid == d_live.rid  # stesso input -> stesso rid, sempre

    class AlwaysFail:
        async def __call__(self, **kwargs):
            raise RuntimeError("down")

    r3 = make(tmp_path / "trace2.jsonl", AlwaysFail())
    d_fallback = request(r3, tick=999)
    assert d_fallback.source == "fallback"
    assert d_fallback.rid  # anche il fallback porta un rid tracciabile
