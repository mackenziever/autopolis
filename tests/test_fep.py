"""Test PostureExperience (Expected Free Energy / Active Inference)."""
from __future__ import annotations

from agents.fep import PostureExperience

POSTURES = ["consolidate_skills", "recover_energy", "seek_social", "push_study"]


def test_no_history_gives_neutral_prior():
    exp = PostureExperience(POSTURES)
    for p in POSTURES:
        assert exp.expected_free_energy(p) == 0.0


def test_good_outcomes_lower_expected_free_energy():
    exp = PostureExperience(POSTURES)
    exp.record_outcome("recover_energy", 0.9)
    exp.record_outcome("recover_energy", 0.9)
    exp.record_outcome("recover_energy", 0.9)
    g = exp.expected_free_energy("recover_energy")
    assert g < 0.0  # reward alto e stabile -> G basso (buono, convenzione Friston)


def test_bad_outcomes_raise_expected_free_energy():
    exp = PostureExperience(POSTURES)
    exp.record_outcome("seek_social", -0.8)
    exp.record_outcome("seek_social", -0.8)
    g = exp.expected_free_energy("seek_social")
    assert g > 0.0


def test_best_posture_prefers_lower_g():
    exp = PostureExperience(POSTURES)
    exp.record_outcome("push_study", 0.9)
    exp.record_outcome("recover_energy", -0.9)
    assert exp.best_posture(POSTURES) == "push_study"


def test_state_round_trip():
    exp = PostureExperience(POSTURES)
    exp.record_outcome("consolidate_skills", 0.5)
    exp.record_outcome("consolidate_skills", -0.2)
    state = exp.to_state()

    restored = PostureExperience(POSTURES)
    restored.load_state(state)
    assert restored.expected_free_energy("consolidate_skills") == exp.expected_free_energy(
        "consolidate_skills"
    )


def test_reward_clamped_to_valid_range():
    exp = PostureExperience(POSTURES)
    exp.record_outcome("push_study", 5.0)
    exp.record_outcome("push_study", -5.0)
    # entrambi clampati a [-1, 1]: media attesa 0 -> G = pragmatic(0) + epistemic(std=1 -> 0.5*0.3)
    g = exp.expected_free_energy("push_study")
    assert -0.2 < g < 0.2
