"""Golden tests per il contratto spatial (baseline Python / futuro Rust)."""
from __future__ import annotations

import json
from pathlib import Path

from engine.spatial_backend import make_spatial_backend
from world.map import CityMap

GOLDEN = Path(__file__).resolve().parent / "golden" / "spatial_seed42.json"


def _build_golden() -> dict:
    city = CityMap(64, 64, 42, 0.08)
    py = make_spatial_backend(city, backend="python", use_hash=False)
    hashed = make_spatial_backend(city, backend="python", use_hash=True, cell=4.0)
    path = py.astar((6, 6), (54, 10))
    positions = {f"agent_{i:03d}": (i % 20, (i * 3) % 20) for i in range(30)}
    pairs = py.all_pairs_near(positions, 4.0)
    pairs_h = hashed.all_pairs_near(positions, 4.0)
    return {
        "seed": 42,
        "astar": {"start": [6, 6], "goal": [54, 10], "path": [list(p) for p in path]},
        "pairs": [[a, b] for a, b in pairs],
        "pairs_hash": [[a, b] for a, b in pairs_h],
    }


def test_generate_or_match_spatial_golden():
    data = _build_golden()
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    if not GOLDEN.exists():
        GOLDEN.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert data["astar"] == expected["astar"]
    assert data["pairs"] == expected["pairs"]
    assert data["pairs_hash"] == expected["pairs_hash"]
    # hash e brute-force devono coincidere
    assert data["pairs"] == data["pairs_hash"]


def test_rust_backend_falls_back_without_extension():
    city = CityMap(64, 64, 7, 0.05)
    backend = make_spatial_backend(city, backend="rust", use_hash=True)
    path = backend.astar((1, 1), (10, 10))
    assert path[0] == (1, 1)
    assert isinstance(path[-1], tuple)
