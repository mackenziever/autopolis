"""Test AGI-OS kernel."""
from __future__ import annotations

import tempfile
from pathlib import Path

from agents.agi_os import SOUL_EXCERPT_MAX, AgiOsKernel, _load_soul_text
from agents.cognitive import AgentCognitiveEngine
from agents.models import AgentRuntime
from agents.persona import generate_persona
from agents.vault_skills import inject_skill
from llm.router import CognitiveRouter


def test_agi_os_boot_prompt_contains_os_id():
    p = generate_persona(0, 42)
    r = AgentRuntime("agent_000", 0, p, (1, 1))
    k = AgiOsKernel(r, strategy="test-strategy")
    out = k.boot_prompt("BASE PROMPT")
    assert "agi_os_agent_000" in out
    assert "--- AGI-OS ---" in out
    assert "BASE PROMPT" in out
    assert k.boot_count == 1
    st = k.heartbeat_state()
    assert st["living"] is True
    assert st["os_id"] == "agi_os_agent_000"


def test_agi_os_soul_excerpt_capped_for_freellm():
    soul = Path(tempfile.mkdtemp()) / "SOUL.md"
    soul.write_text("S" * (SOUL_EXCERPT_MAX + 500), encoding="utf-8")
    _load_soul_text.cache_clear()
    p = generate_persona(0, 42)
    r = AgentRuntime("agent_000", 0, p, (1, 1))
    k = AgiOsKernel(r, soul_path=soul, strategy="test-strategy")
    excerpt = k.soul_excerpt()
    assert len(excerpt) <= SOUL_EXCERPT_MAX + 2  # + ellipsis
    out = k.boot_prompt("BASE")
    assert "--- AGI-OS ---" in out
    assert "soul:" in out
    # boot_prompt must not embed the uncapped soul
    assert "S" * (SOUL_EXCERPT_MAX + 100) not in out


def test_cognitive_prompt_includes_agi_os_and_skill_inject():
    tmp = Path(tempfile.mkdtemp()) / "t.jsonl"
    p = generate_persona(1, 42)
    r = AgentRuntime("agent_001", 1, p, (2, 2))
    router = CognitiveRouter(False, "mock", "", 1.0, 1, str(tmp), 42)
    cog = AgentCognitiveEngine(r, router, 42, 8)
    prompt = cog.prompt()
    assert "agi_os_agent_001" in prompt
    assert "--- AGI-OS ---" in prompt
    with_skill = inject_skill(prompt, "daily_reflection")
    assert with_skill.startswith(prompt) or "--- SKILL" in with_skill
    assert router.stats.get("last_latency_ms") == 0.0
