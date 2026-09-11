"""Spatial Hash Grid: query di prossimita' O(1) medio, deterministico.

Contratto allineato a SpatialService.all_pairs_near: restituisce coppie ordinate
(a_id < b_id) cosi' social/economy restano riproducibili.
Preparato per sostituzione Rust/PyO3 con la stessa API.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from config import Coord


class SpatialHashGrid:
    def __init__(self, cell_size: float = 4.0):
        if cell_size <= 0:
            raise ValueError("cell_size must be > 0")
        self.cell_size = float(cell_size)
        self._cells: Dict[Tuple[int, int], List[str]] = defaultdict(list)
        self._pos: Dict[str, Coord] = {}

    def clear(self) -> None:
        self._cells.clear()
        self._pos.clear()

    def _cell(self, pos: Coord) -> Tuple[int, int]:
        return (int(pos[0] // self.cell_size), int(pos[1] // self.cell_size))

    def rebuild(self, positions: Dict[str, Coord]) -> None:
        self.clear()
        for aid, pos in positions.items():
            self._pos[aid] = pos
            self._cells[self._cell(pos)].append(aid)

    def query_radius(self, center: Coord, radius: float) -> List[str]:
        r2 = radius * radius
        cx, cy = self._cell(center)
        reach = int(radius // self.cell_size) + 1
        out: List[str] = []
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for aid in self._cells.get((cx + dx, cy + dy), ()):
                    px, py = self._pos[aid]
                    if (px - center[0]) ** 2 + (py - center[1]) ** 2 <= r2:
                        out.append(aid)
        out.sort()
        return out

    def all_pairs_near(self, positions: Dict[str, Coord], radius: float) -> List[Tuple[str, str]]:
        self.rebuild(positions)
        r2 = radius * radius
        pairs = set()
        for aid, pos in positions.items():
            for other in self.query_radius(pos, radius):
                if other == aid:
                    continue
                a, b = (aid, other) if aid < other else (other, aid)
                ox, oy = positions[other]
                if (pos[0] - ox) ** 2 + (pos[1] - oy) ** 2 <= r2:
                    pairs.add((a, b))
        return sorted(pairs)
