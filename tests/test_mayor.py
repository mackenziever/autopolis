"""Sindaco (agents/mayor.py): ratifica/veta le proposte chiuse, decide i pareggi.

Verifica sia la parte pura/deterministica (world/governance.py.tick_day con
mayor_rulings, retrocompatibile senza), sia MayorOffice.rule_on_proposal con
un transport LLM fake (stesso pattern di tests/test_escalation.py)."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from agents.mayor import MayorOffice
from llm.router import CognitiveRouter
from world.governance import GovernanceBoard


def _propose_and_vote(
    board: GovernanceBoard,
    *,
    tick: int,
    day: int,
    votes: dict,
    kind: str = "noise_fine",
    proposer_id: str = "agent_000",
    value=None,
):
    prop, _money, _ev = board.propose(
        tick=tick, day=day, proposer_id=proposer_id, kind=kind, runtime_money=100.0, value=value
    )
    assert prop is not None
    for voter, vote in votes.items():
        board.cast_vote(tick=tick, proposal_id=prop.proposal_id, voter_id=voter, vote=vote)
    return prop


def test_tick_day_without_mayor_unchanged():
    """Retrocompatibilita': senza mayor_rulings, yes>no passa, pareggio non passa."""
    board = GovernanceBoard(seed=1, day_length=600)
    passing = _propose_and_vote(
        board, tick=0, day=0, votes={"a": "yes", "b": "yes", "c": "no"}, kind="noise_fine"
    )
    tie = _propose_and_vote(
        board, tick=0, day=0, votes={"a": "yes", "b": "no"}, kind="overcrowding_limit",
        proposer_id="agent_001",
    )
    events = board.tick_day(day=10, tick=10 * 600)
    assert board.proposals[passing.proposal_id].status == "passed"
    assert board.proposals[tie.proposal_id].status == "rejected"
    assert not any(e["type"] == "mayor_ruling" for e in events)


def test_tick_day_mayor_can_veto_a_popular_proposal():
    board = GovernanceBoard(seed=1, day_length=600)
    prop = _propose_and_vote(
        board, tick=0, day=0, votes={"a": "yes", "b": "yes", "c": "no"}, kind="noise_fine"
    )
    ruling = {
        "final": False,
        "choice": "veto",
        "thought": "Multa eccessiva per la citta'.",
        "confidence": 0.7,
        "tie_break": False,
    }
    events = board.tick_day(day=10, tick=10 * 600, mayor_rulings={prop.proposal_id: ruling})
    assert board.proposals[prop.proposal_id].status == "rejected"
    mayor_events = [e for e in events if e["type"] == "mayor_ruling"]
    assert len(mayor_events) == 1
    assert mayor_events[0]["final"] is False
    assert mayor_events[0]["tie_break"] is False


def test_tick_day_mayor_tie_break_passes_proposal():
    board = GovernanceBoard(seed=1, day_length=600)
    prop = _propose_and_vote(
        board, tick=0, day=0, votes={"a": "yes", "b": "no"}, kind="overcrowding_limit",
        value=5,
    )
    ruling = {
        "final": True,
        "choice": "yes",
        "thought": "Decido io: passa.",
        "confidence": 0.6,
        "tie_break": True,
    }
    events = board.tick_day(day=10, tick=10 * 600, mayor_rulings={prop.proposal_id: ruling})
    assert board.proposals[prop.proposal_id].status == "passed"
    assert board.active_rules["max_agents_per_poi"] == 5  # default (999) sovrascritto
    mayor_events = [e for e in events if e["type"] == "mayor_ruling"]
    assert mayor_events[0]["tie_break"] is True


def test_proposals_closing_now_only_active_expired():
    board = GovernanceBoard(seed=1, day_length=600)
    prop = _propose_and_vote(board, tick=0, day=0, votes={}, kind="noise_fine")
    assert board.proposals_closing_now(tick=100) == []
    closing = board.proposals_closing_now(tick=prop.closes_tick)
    assert len(closing) == 1
    assert closing[0].proposal_id == prop.proposal_id
    # Chiusa: non deve piu' comparire come "closing now" ad un tick successivo.
    board.tick_day(day=10, tick=prop.closes_tick)
    assert board.proposals_closing_now(tick=prop.closes_tick + 1) == []


def _mayor_with_transport(choice: str):
    trace_path = str(Path(tempfile.mkdtemp()) / "mayor_trace.jsonl")

    async def _fake_transport(**kwargs):
        return {"content": f'{{"choice": "{choice}", "thought": "motivazione test", "confidence": 0.8}}'}

    router = CognitiveRouter(True, "agnes-2.5-flash", "", 1.0, 1, trace_path, 42, transport=_fake_transport)
    return MayorOffice(router)


def test_mayor_tie_break_yes_wins():
    mayor = _mayor_with_transport("yes")
    board = GovernanceBoard(seed=1, day_length=600)
    prop = _propose_and_vote(board, tick=0, day=0, votes={"a": "yes", "b": "no"})
    yes, no, abstain = board.tally(prop)
    ruling = asyncio.run(mayor.rule_on_proposal(0, prop, yes=yes, no=no, abstain=abstain))
    assert ruling["tie_break"] is True
    assert ruling["final"] is True
    assert mayor.stats["tie_breaks"] == 1
    assert mayor.stats["rulings"] == 1


def test_mayor_ratifies_popular_proposal():
    mayor = _mayor_with_transport("ratify")
    board = GovernanceBoard(seed=1, day_length=600)
    prop = _propose_and_vote(board, tick=0, day=0, votes={"a": "yes", "b": "yes", "c": "no"})
    yes, no, abstain = board.tally(prop)
    ruling = asyncio.run(mayor.rule_on_proposal(0, prop, yes=yes, no=no, abstain=abstain))
    assert ruling["tie_break"] is False
    assert ruling["final"] is True
    assert mayor.stats["ratified"] == 1


def test_mayor_vetoes_popular_proposal():
    mayor = _mayor_with_transport("veto")
    board = GovernanceBoard(seed=1, day_length=600)
    prop = _propose_and_vote(board, tick=0, day=0, votes={"a": "yes", "b": "yes", "c": "no"})
    yes, no, abstain = board.tally(prop)
    ruling = asyncio.run(mayor.rule_on_proposal(0, prop, yes=yes, no=no, abstain=abstain))
    assert ruling["final"] is False
    assert mayor.stats["vetoed"] == 1


def test_engine_mayor_disabled_without_llm_key(monkeypatch):
    """Se MAYOR_LLM_API_KEY (o endpoint/modello) non sono nell'ambiente,
    self.mayor resta None — mai bloccante, stesso principio del resto del
    progetto (offline -> fallback)."""
    monkeypatch.delenv("MAYOR_LLM_API_KEY", raising=False)
    monkeypatch.delenv("MAYOR_LLM_API_BASE", raising=False)
    monkeypatch.delenv("MAYOR_LLM_MODEL", raising=False)
    from config import SimConfig
    from engine.tick_engine import CivitasEngine

    cfg = SimConfig(num_agents=1, total_ticks=1, llm_enabled=False, governance_enabled=True)
    engine = CivitasEngine(cfg)
    assert engine.mayor is None
