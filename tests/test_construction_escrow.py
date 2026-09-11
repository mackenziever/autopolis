"""Agent-funded escrow construction (Cafe reel parity)."""
from __future__ import annotations

from world.construction import BUILD_CATALOG, ConstructionBoard, RelocateProject
from world.map import CityMap


def test_propose_escrow_and_complete_cafe():
    board = ConstructionBoard(seed=7, day_length=600)
    city = CityMap(64, 64, seed=7, obstacle_density=0.08)
    # Founder deposits founder_min
    proj, money, ev = board.propose(
        tick=10, day=0, founder_id="agent_000", kind="cafe", runtime_money=50.0
    )
    assert ev["type"] == "build_propose"
    assert money == 50.0 - BUILD_CATALOG["cafe"]["founder_min"]
    assert proj is not None and proj.status == "funding"
    # Peers fund remainder
    remaining = proj.cost - proj.escrow
    money2, ev2 = board.contribute(
        tick=11, agent_id="agent_001", amount=remaining, runtime_money=100.0
    )
    assert ev2["type"] == "build_contribute"
    assert proj.funded() and proj.status == "building"
    # Not enough days yet
    assert board.tick_day(day=0, tick=12, city_map=city) == []
    # After build_days
    done = board.tick_day(day=2, tick=1300, city_map=city)
    assert len(done) == 1
    assert done[0]["poi"] == "AgentCafe"
    assert done[0]["source"] == "agent_escrow"
    assert "AgentCafe" in city.pois
    board.record_visit("AgentCafe", "agent_002")
    board.record_visit("AgentCafe", "agent_003")
    assert board.stats["attendance_peak"] >= 2


def test_suggest_social_poi_pulls_to_site():
    board = ConstructionBoard(seed=1)
    board.propose(tick=0, day=0, founder_id="a", kind="market_stall", runtime_money=50)
    # Force funded+building quickly
    p = board.open_projects()[0]
    p.escrow = p.cost
    p.status = "building"
    hits = sum(
        1
        for i in range(40)
        if board.suggest_social_poi(f"agent_{i:03d}", tick=100) != "Plaza"
    )
    assert hits >= 10


def test_join_crew_targets_specific_project_not_always_first():
    """BUGFIX: prima join_crew() senza project_id prendeva sempre
    open_relocations()[0] — con piu' rilocazioni aperte in parallelo, ogni
    join finiva sul primo progetto affamando gli altri. Ora un project_id
    esplicito deve unire ESATTAMENTE quel progetto."""
    board = ConstructionBoard(seed=1)
    first = RelocateProject(
        project_id="reloc_aaa", poi="Cafe", from_xy=(1, 1), to_xy=(2, 2), proposer_id="agent_000"
    )
    second = RelocateProject(
        project_id="reloc_bbb", poi="Gym", from_xy=(3, 3), to_xy=(4, 4), proposer_id="agent_001"
    )
    board.relocations[first.project_id] = first
    board.relocations[second.project_id] = second

    ev = board.join_crew(tick=0, agent_id="agent_002", project_id="reloc_bbb")
    assert ev is not None
    assert ev["project_id"] == "reloc_bbb"
    assert "agent_002" in second.crew
    assert "agent_002" not in first.crew

    ev2 = board.join_crew(tick=0, agent_id="agent_003", project_id="reloc_aaa")
    assert ev2["project_id"] == "reloc_aaa"
    assert "agent_003" in first.crew
    assert "agent_003" not in second.crew


def test_relocate_target_never_overlaps_existing_poi():
    """Bugfix (2026-09-11, "edifici sovrapposti" segnalato dall'utente in
    produzione): walkable() da solo non basta, register_poi() libera l'area
    7x7 attorno a ogni POI esistente quindi la sua piastrella esatta risulta
    "walkable". _deterministic_relocate_target() deve scartare ogni candidato
    troppo vicino (Chebyshev < MIN_POI_SPACING) a un altro POI registrato."""
    from types import SimpleNamespace

    from agents.state_machine import MIN_POI_SPACING, AgentFSM
    from engine.spatial import SpatialService

    city = CityMap(64, 64, seed=3, obstacle_density=0.0)
    # Registra parecchi POI vicini fra loro per costringere la ricerca a
    # scartare piu' candidati (altrimenti il primo tentativo passerebbe sempre).
    for i, (x, y) in enumerate([(30, 30), (32, 30), (34, 30), (30, 32), (34, 34)]):
        city.register_poi(f"Blob{i}", (x, y))
    city.register_poi("Cafe", (32, 32))

    fake_agent = SimpleNamespace(
        spatial=SpatialService(city),
        r=SimpleNamespace(agent_id="agent_007"),
    )
    target = AgentFSM._deterministic_relocate_target(fake_agent, "Cafe")
    assert target is not None
    occupied = [xy for name, xy in city.pois.items() if name != "Cafe"]
    for ox, oy in occupied:
        assert max(abs(target[0] - ox), abs(target[1] - oy)) >= MIN_POI_SPACING
