"""Test Paperclip-city: board, checkout, complete, idempotenza giornaliera."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from config import SimConfig
from engine.tick_engine import CivitasEngine
from paperclip_city import Board, make_issue_id
from paperclip_city.models import COGNITIVE_KINDS


@pytest.fixture
def board(tmp_path: Path) -> Board:
    return Board(tmp_path / "paperclip", seed=42)


def test_deterministic_issue_ids():
    a = make_issue_id(42, "agent_001", 0, "reflect")
    b = make_issue_id(42, "agent_001", 0, "reflect")
    c = make_issue_id(42, "agent_001", 0, "career")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_create_daily_issues(board: Board):
    agents = ["agent_000", "agent_001"]
    n = board.create_daily_issues(agents, day=0, tick=10)
    assert n == len(agents) * len(COGNITIVE_KINDS)
    assert len(board.issues) == n


def test_create_daily_issues_idempotent(board: Board):
    agents = ["agent_000"]
    first = board.create_daily_issues(agents, day=0, tick=0)
    second = board.create_daily_issues(agents, day=0, tick=100)
    assert first == len(COGNITIVE_KINDS)
    assert second == 0
    assert len(board.issues) == len(COGNITIVE_KINDS)


def test_checkout_and_complete(board: Board):
    agents = ["agent_000"]
    board.create_daily_issues(agents, day=1, tick=600)
    issue = board.find_issue("agent_000", 1, "reflect")
    assert issue is not None
    assert issue.status == "todo"

    checked = board.checkout("agent_000", issue.id, tick=650)
    assert checked is not None
    assert checked.status == "in_progress"

    done = board.complete(issue.id, "Consolidare skill coding.", tick=700)
    assert done is not None
    assert done.status == "done"
    assert "coding" in (done.result or "")


def test_complete_is_idempotent(board: Board):
    board.create_daily_issues(["agent_000"], day=0, tick=0)
    issue = board.find_issue("agent_000", 0, "career")
    assert issue is not None
    board.checkout("agent_000", issue.id, tick=70)
    board.complete(issue.id, "Prima", tick=71)
    again = board.complete(issue.id, "Seconda", tick=72)
    assert again is not None
    assert again.result == "Prima"


def test_list_inbox(board: Board):
    board.create_daily_issues(["agent_000", "agent_001"], day=0, tick=0)
    inbox = board.list_inbox("agent_000")
    assert len(inbox) == len(COGNITIVE_KINDS)
    todo = board.list_inbox("agent_000", status="todo")
    assert len(todo) == len(COGNITIVE_KINDS)


def test_persist_and_reload(tmp_path: Path):
    data_dir = tmp_path / "pc"
    b1 = Board(data_dir, seed=7)
    b1.create_daily_issues(["agent_000"], day=0, tick=0)
    issue = b1.find_issue("agent_000", 0, "social")
    assert issue is not None
    b1.complete(issue.id, "networking", tick=430)

    b2 = Board(data_dir, seed=7)
    reloaded = b2.find_issue("agent_000", 0, "social")
    assert reloaded is not None
    assert reloaded.status == "done"
    assert reloaded.result == "networking"


def test_stats(board: Board):
    board.create_daily_issues(["agent_000"], day=0, tick=0)
    s = board.stats()
    assert s["paperclip_open"] == len(COGNITIVE_KINDS)
    assert s["paperclip_done"] == 0
    issue = board.find_issue("agent_000", 0, "study")
    assert issue is not None
    board.checkout("agent_000", issue.id, tick=330)
    board.complete(issue.id, "focus coding", tick=331)
    s2 = board.stats()
    assert s2["paperclip_done"] == 1
    assert s2["paperclip_open"] == len(COGNITIVE_KINDS) - 1


def test_engine_smoke_with_paperclip(tmp_path: Path):
    log = str(tmp_path / "replay.msgpack")
    pc_dir = str(tmp_path / "paperclip")
    cfg = SimConfig(
        num_agents=5,
        total_ticks=50,
        seed=42,
        log_path=log,
        paperclip_city_enabled=True,
        paperclip_city_path=pc_dir,
    )
    asyncio.run(CivitasEngine(cfg).run(realtime=False))
    board = Board(pc_dir, seed=42)
    assert board.stats()["paperclip_total"] >= len(COGNITIVE_KINDS) * 5
    assert (Path(pc_dir) / "issues.jsonl").exists()
