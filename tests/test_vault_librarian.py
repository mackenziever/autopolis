"""Vault librarian + research curation."""
from __future__ import annotations

from knowledge.vault_librarian import VaultLibrarian
from agents.research import ResearchLoop
from llm.router import CognitiveRouter


def test_librarian_writes_organized(tmp_path):
    lib = VaultLibrarian(vault_root=tmp_path, alveare=None)
    r = lib.record_lesson(
        agent_id="agent_000",
        event="reflection",
        choice="push_study",
        lesson="Studiare coding accelera la carriera.",
        tick=10,
        topic="study",
    )
    assert r["ok"]
    assert (tmp_path / "04-LEARNINGS" / "agents" / "agent_000.md").exists()
    assert (tmp_path / "04-LEARNINGS" / "by-topic" / "study.md").exists()
    assert (tmp_path / "00-META" / "KNOWLEDGE-CATALOG.md").exists()
    lib.record_discovery(title="Cafe escrow", body="Gli agenti finanziano i POI.", agent_id="agent_001", tick=11)
    assert (tmp_path / "06-MEMORY" / "wiki" / "discovered" / "cafe-escrow.md").exists()
    lib.record_world_build(poi="AgentCafe", meta={"source": "agent_escrow", "description": "ok"}, tick=12)
    assert (tmp_path / "03-WORLD" / "built-pois.md").exists()


def test_curate_event_city_build(tmp_path):
    lib = VaultLibrarian(vault_root=tmp_path)
    loop = ResearchLoop(CognitiveRouter(False, "x", "http://x", 1, 1, str(tmp_path/"t.jsonl"), 1), lib)
    out = loop.curate_event(
        {"type": "city_build", "tick": 5, "poi": "Library", "source": "growth", "description": "unlock"}
    )
    assert out and out.get("poi") == "Library"
