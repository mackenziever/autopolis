"""ResearchLoop (agents/research.py): scrittura vault/Alveare del research loop.

Bugfix (2026-09-11, "gli agenti non si automigliorano"): quando il router va in
fallback (offline / budget esaurito), la scelta fra write_lesson/write_discovery/
skip_research resta comunque deterministica (hash sul rid, non sul contenuto) —
senza un controllo esplicito su Decision.source, il placeholder "Fallback
deterministico per research_focus (...)" veniva scritto nel vault/Alveare come
se fosse una vera scoperta, poi ripescato da altri agenti come RAG hit,
auto-contaminando la base di conoscenza condivisa con rumore invece che con
sapere reale. Stesso principio gia' applicato a agents/cognitive.py.reflect()."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from agents.research import ResearchLoop
from knowledge.vault_librarian import VaultLibrarian
from llm.router import CognitiveRouter
from llm.schemas import Decision


def _loop(tmp_path: Path) -> ResearchLoop:
    router = CognitiveRouter(False, "mock", "http://x", 1.0, 1, str(tmp_path / "t.jsonl"), 42)
    librarian = VaultLibrarian(vault_root=tmp_path / "vault")
    return ResearchLoop(router, librarian)


def _run(loop: ResearchLoop, **kwargs):
    return asyncio.run(
        loop.research_agent(
            agent_id=kwargs.pop("agent_id", "agent_000"),
            tick=kwargs.pop("tick", 0),
            prompt="Sei un agente di Civitas.",
            **kwargs,
        )
    )


def test_fallback_decision_is_never_written_to_vault(tmp_path):
    loop = _loop(tmp_path)
    # Il router "sceglie" write_discovery ma la fonte e' fallback: non deve
    # scrivere nulla, a prescindere da cosa dice choices[idx] internamente.
    loop.router.decide = AsyncMock(
        return_value=Decision(
            choice="write_discovery",
            thought="Fallback deterministico per research_focus (offline).",
            confidence=0.5,
            source="fallback",
        )
    )
    out = _run(loop)
    assert out["choice"] == "skip_research"
    assert out["stored"] is False
    assert out["self_improve"] is False
    assert loop.stats["fallback_skipped"] == 1
    assert loop.stats["writes"] == 0
    assert not (tmp_path / "vault" / "06-MEMORY" / "wiki" / "discovered").exists()


def test_live_decision_is_written_to_vault(tmp_path):
    loop = _loop(tmp_path)
    loop.router.decide = AsyncMock(
        return_value=Decision(
            choice="write_discovery",
            thought="Ho scoperto che le griglie a 12 colonne migliorano la leggibilità.",
            confidence=0.9,
            source="live",
        )
    )
    out = _run(loop)
    assert out["choice"] == "write_discovery"
    assert out["stored"] is True
    assert out["self_improve"] is True
    assert loop.stats["fallback_skipped"] == 0
    assert loop.stats["writes"] == 1
    discovered = tmp_path / "vault" / "06-MEMORY" / "wiki" / "discovered"
    assert discovered.exists() and any(discovered.iterdir())


def test_skip_research_choice_never_writes_regardless_of_source(tmp_path):
    loop = _loop(tmp_path)
    loop.router.decide = AsyncMock(
        return_value=Decision(choice="skip_research", thought="Niente di nuovo oggi.", confidence=0.6, source="live")
    )
    out = _run(loop)
    assert out["stored"] is False
    assert loop.stats["writes"] == 0


def test_rid_is_persisted_in_discovery_and_lesson_files(tmp_path):
    """Approfondimento RSI (2026-09-11): il rid della richiesta LLM che ha
    originato una scoperta/lezione deve finire nel file scritto, per chiudere
    il loop di audit fra vault e la chiamata esatta che l'ha prodotta."""
    loop = _loop(tmp_path)
    loop.router.decide = AsyncMock(
        return_value=Decision(
            choice="write_discovery",
            thought="Le palette scure con bande cyan reggono bene il bloom.",
            confidence=0.85,
            source="live",
            rid="deadbeef1234",
        )
    )
    _run(loop)
    discovered = tmp_path / "vault" / "06-MEMORY" / "wiki" / "discovered"
    files = list(discovered.iterdir())
    assert files
    content = files[0].read_text(encoding="utf-8")
    assert "rid: deadbeef1234" in content

    loop2 = _loop(tmp_path)
    loop2.router.decide = AsyncMock(
        return_value=Decision(
            choice="write_lesson",
            thought="Studiare al mattino funziona meglio.",
            confidence=0.7,
            source="live",
            rid="cafef00d5678",
        )
    )
    _run(loop2)
    lesson_file = tmp_path / "vault" / "04-LEARNINGS" / "agents" / "agent_000.md"
    assert "rid=cafef00d5678" in lesson_file.read_text(encoding="utf-8")
