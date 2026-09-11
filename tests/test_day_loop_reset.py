"""Day-boundary contract: FSM day flags re-enable without mid-day reset."""
from __future__ import annotations

from types import SimpleNamespace

from living_server.day_loop import (
    DAY_DECISION_FLAG_ATTRS,
    agents_ready_for_new_day,
    daily_decision_pending,
)


def test_daily_decision_pending_keys_off_day_inequality():
    assert daily_decision_pending(-1, 0) is True
    assert daily_decision_pending(0, 0) is False
    assert daily_decision_pending(0, 1) is True
    assert daily_decision_pending(5, 6) is True


def test_agents_ready_for_new_day_after_boundary():
    agents = [
        SimpleNamespace(r=SimpleNamespace(reflected_day=2)),
        SimpleNamespace(r=SimpleNamespace(reflected_day=-1)),
    ]
    assert agents_ready_for_new_day(agents, day=3) is True
    agents[0].r.reflected_day = 3
    assert agents_ready_for_new_day(agents, day=3) is False


def test_day_flag_attrs_match_fsm_contract():
    assert "reflected_day" in DAY_DECISION_FLAG_ATTRS
    assert "career_decided_day" in DAY_DECISION_FLAG_ATTRS
    assert "study_focused_day" in DAY_DECISION_FLAG_ATTRS
    assert "social_decided_day" in DAY_DECISION_FLAG_ATTRS
    assert "exam_attempted_day" in DAY_DECISION_FLAG_ATTRS
