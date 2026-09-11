"""Contratto spatial sostituibile (Python baseline | Rust/PyO3 opzionale).

L'estensione nativa deve esportare:
  astar(blocked, w, h, start, goal, diagonal) -> list[tuple[int,int]]
  all_pairs_near(ids, xy, radius) -> list[tuple[str,str]]
con ordinamento stabile identico alla baseline.
"""
from __future__ import annotations

from typing import Dict, List, Protocol, Tuple

from config import Coord
from engine.spatial import SpatialService
from engine.spatial_hash import SpatialHashGrid
from world.map import CityMap


class SpatialBackend(Protocol):
    def astar(self, start: Coord, goal: Coord) -> List[Coord]: ...
    def all_pairs_near(
        self, positions: Dict[str, Coord], radius: float
    ) -> List[Tuple[str, str]]: ...


class PythonSpatialBackend:
    def __init__(self, city: CityMap, *, diagonal: bool = False, use_hash: bool = False, cell: float = 4.0):
        self.service = SpatialService(city, diagonal)
        self.hash = SpatialHashGrid(cell) if use_hash else None

    def astar(self, start: Coord, goal: Coord) -> List[Coord]:
        return self.service.astar(start, goal)

    def all_pairs_near(self, positions: Dict[str, Coord], radius: float) -> List[Tuple[str, str]]:
        if self.hash is not None:
            return self.hash.all_pairs_near(positions, radius)
        return self.service.all_pairs_near(positions, radius)

    @property
    def cache_stats(self) -> dict:
        return {
            "hits": getattr(self.service, "cache_hits", 0),
            "misses": getattr(self.service, "cache_misses", 0),
            "size": len(self.service._path_cache),
        }


class RustSpatialBackend:
    """Wrapper PyO3: se il modulo `civitas_spatial` manca, solleva ImportError."""

    def __init__(self, city: CityMap, *, diagonal: bool = False, use_hash: bool = True, cell: float = 4.0):
        import civitas_spatial  # type: ignore

        self._mod = civitas_spatial
        self.city = city
        self.diagonal = diagonal
        self.use_hash = use_hash
        self.cell = cell
        snap = city.snapshot()
        self._blocked = list(snap.blocked_cells)
        self._fallback = PythonSpatialBackend(city, diagonal=diagonal, use_hash=use_hash, cell=cell)
        # AgentFSM continua su A* Python finche' il modulo nativo non e' golden-verified.
        self.service = self._fallback.service
        self.hash = self._fallback.hash

    def astar(self, start: Coord, goal: Coord) -> List[Coord]:
        try:
            path = self._mod.astar(
                self._blocked, self.city.width, self.city.height, start, goal, self.diagonal
            )
            return [tuple(p) for p in path]
        except Exception:
            return self._fallback.astar(start, goal)

    def all_pairs_near(self, positions: Dict[str, Coord], radius: float) -> List[Tuple[str, str]]:
        ids = sorted(positions)
        xy = [positions[i] for i in ids]
        try:
            pairs = self._mod.all_pairs_near(ids, xy, float(radius))
            return [(a, b) for a, b in pairs]
        except Exception:
            return self._fallback.all_pairs_near(positions, radius)

    @property
    def cache_stats(self) -> dict:
        return self._fallback.cache_stats


def make_spatial_backend(
    city: CityMap,
    *,
    backend: str = "python",
    diagonal: bool = False,
    use_hash: bool = False,
    cell: float = 4.0,
) -> SpatialBackend:
    name = (backend or "python").lower()
    if name == "rust":
        try:
            return RustSpatialBackend(city, diagonal=diagonal, use_hash=use_hash, cell=cell)
        except ImportError:
            return PythonSpatialBackend(city, diagonal=diagonal, use_hash=use_hash, cell=cell)
    return PythonSpatialBackend(city, diagonal=diagonal, use_hash=use_hash, cell=cell)
