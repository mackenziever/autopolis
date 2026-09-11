"""Wilderness: cittadini possono uscire dalla griglia città."""
from __future__ import annotations

from config import WILDERNESS_LANDMARKS, SimConfig
from engine.spatial import SpatialService
from world.map import CityMap


def test_wilderness_landmarks_in_bounds_and_walkable():
    m = CityMap(64, 64, seed=42, wilderness_margin=24)
    assert m.margin == 24
    for name, xy in WILDERNESS_LANDMARKS.items():
        assert name in m.pois
        assert m.pois[name] == xy
        assert not m.in_city(xy)
        assert m.in_bounds(xy)
        assert m.walkable(xy)


def test_astar_reaches_wild_north():
    m = CityMap(64, 64, seed=42, wilderness_margin=24)
    s = SpatialService(m)
    path = s.astar((32, 32), WILDERNESS_LANDMARKS["Wild_North"])
    assert path[0] == (32, 32)
    assert path[-1] == WILDERNESS_LANDMARKS["Wild_North"]
    assert any(y < 0 for _, y in path)


def test_simconfig_wilderness_margin_default():
    cfg = SimConfig()
    assert cfg.wilderness_margin >= 14
    for _, (x, y) in WILDERNESS_LANDMARKS.items():
        assert -cfg.wilderness_margin <= x < cfg.grid_w + cfg.wilderness_margin
        assert -cfg.wilderness_margin <= y < cfg.grid_h + cfg.wilderness_margin
