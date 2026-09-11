"""Unit tests for RoomBoard mutable environments."""
from world.room_board import PROP_CATALOG, THEME_CATALOG, RoomBoard, RoomProp


def test_seed_and_default_props():
    board = RoomBoard(seed=3)
    board.seed_pois(["Home", "Cafe"])
    home = board.rooms["Home"]
    assert home.theme == "cyberpunk"
    assert len(home.props) == 2
    assert {p.kind for p in home.props} == {"plant", "desk"}


def test_set_theme_costs_money():
    board = RoomBoard(seed=1)
    board.ensure_room("Plaza")
    money, ev = board.apply(
        tick=10, agent_id="a1", poi="Plaza", choice="set_theme_warm", runtime_money=5.0
    )
    assert money == 4.0
    assert ev["type"] == "room_apply"
    assert ev["theme"] == "warm"
    assert board.rooms["Plaza"].theme == "warm"
    assert "a1" in board.rooms["Plaza"].stewards


def test_add_and_remove_prop():
    board = RoomBoard(seed=2)
    board.ensure_room("Cafe")
    money, ev = board.apply(
        tick=1, agent_id="a2", poi="Cafe", choice="add_prop_sofa", runtime_money=10.0
    )
    assert ev["action"] == "add_prop"
    assert money == round(10.0 - PROP_CATALOG["sofa"]["cost"], 3)
    assert any(p.kind == "sofa" for p in board.rooms["Cafe"].props)
    money2, ev2 = board.apply(
        tick=2, agent_id="a2", poi="Cafe", choice="remove_prop_sofa", runtime_money=money
    )
    assert ev2["action"] == "remove_prop"
    assert money2 == money
    assert not any(p.kind == "sofa" for p in board.rooms["Cafe"].props)


def test_choices_respect_funds_and_full():
    board = RoomBoard(seed=4)
    board.ensure_room("Lab")
    choices = board.choices_for("Lab", money=0.3)
    assert "skip_room" in choices
    assert not any(c.startswith("set_theme_") for c in choices)
    assert not any(c.startswith("add_prop_") for c in choices)
    # can still remove defaults
    assert any(c.startswith("remove_prop_") for c in choices)


def test_choices_remove_prop_order_is_deterministic_not_hash_seed():
    """Bugfix determinismo (2026-09-11): `choices_for()` costruiva le voci
    remove_prop_* iterando direttamente un set di stringhe (`{p.kind for p in
    room.props}`), il cui ordine dipende da PYTHONHASHSEED (randomizzato per
    processo in Python), non dal seed della simulazione. Due run identiche
    potevano quindi generare `choices` in ordine diverso -> hash della richiesta
    diverso -> scelta fallback diversa -> divergenza di replay (scoperto
    confrontando tick-by-tick due run con seed/config identici). Ora l'ordine
    deve essere alfabetico, sempre, a prescindere dall'hash seed del processo."""
    board = RoomBoard(seed=7)
    room = board.ensure_room("Studio")
    # props con kind in ordine di inserimento non alfabetico
    room.props = [
        RoomProp(prop_id=f"{kind}_{i}", kind=kind, x=0.0, z=0.0, rot=0.0)
        for i, kind in enumerate(("sofa", "desk", "plant", "bookshelf"))
    ]
    choices = board.choices_for("Studio", money=0.0)
    remove_choices = [c for c in choices if c.startswith("remove_prop_")]
    kinds_in_order = [c[len("remove_prop_") :] for c in remove_choices]
    assert kinds_in_order == sorted(kinds_in_order)
    assert set(kinds_in_order) == {"sofa", "desk", "plant", "bookshelf"}


def test_checkpoint_roundtrip():
    board = RoomBoard(seed=9)
    board.ensure_room("Office")
    board.apply(tick=3, agent_id="x", poi="Office", choice="set_theme_loft", runtime_money=8.0)
    state = board.to_state()
    other = RoomBoard(seed=0)
    other.load_state(state)
    assert other.rooms["Office"].theme == "loft"
    assert other.stats["themes_set"] == 1
    assert set(THEME_CATALOG)
