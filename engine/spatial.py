"""Servizi spaziali deterministici.

Baseline Python/Numpy pronta all'uso. L'interfaccia e' intenzionalmente piccola:
puo' essere rimpiazzata da un'estensione Rust/PyO3 senza toccare gli agenti.
"""
from __future__ import annotations
import heapq
from typing import Dict, Tuple, List, Iterable
import numpy as np
from config import Coord
from world.map import CityMap

class SpatialService:
    def __init__(self, city_map: CityMap, diagonal: bool = False):
        self.map = city_map
        self.diagonal = diagonal
        self._path_cache: Dict[Tuple[Coord, Coord], tuple[Coord, ...]] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    @staticmethod
    def heuristic(a: Coord, b: Coord) -> int:
        return abs(a[0]-b[0]) + abs(a[1]-b[1])

    def astar(self, start: Coord, goal: Coord) -> List[Coord]:
        key = (start, goal)
        cached = self._path_cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return list(cached)
        self.cache_misses += 1
        if start == goal:
            return [start]
        frontier = [(self.heuristic(start, goal), 0, 0, start)]
        came: Dict[Coord, Coord] = {}
        cost: Dict[Coord, int] = {start: 0}
        serial = 1
        found = False
        while frontier:
            _, g, _, cur = heapq.heappop(frontier)
            if cur == goal:
                found = True
                break
            for nxt in self.map.neighbors(cur, self.diagonal):
                ng = g + (14 if nxt[0] != cur[0] and nxt[1] != cur[1] else 10)
                if ng < cost.get(nxt, 1 << 60):
                    cost[nxt] = ng
                    came[nxt] = cur
                    f = ng + 10*self.heuristic(nxt, goal)
                    heapq.heappush(frontier, (f, ng, serial, nxt))
                    serial += 1
        if not found:
            return [start]
        path = [goal]
        cur = goal
        while cur != start:
            cur = came[cur]
            path.append(cur)
        path.reverse()
        if len(self._path_cache) > 50_000:
            self._path_cache.clear()
        self._path_cache[key] = tuple(path)
        return path

    def proximity(self, positions: Dict[str, Coord], center: Coord, radius: float) -> List[str]:
        """Per 50 entita' lo scan vettoriale e' spesso piu' economico di ricreare un KDTree."""
        if not positions:
            return []
        ids = list(positions)
        a = np.asarray([positions[i] for i in ids], dtype=np.float32)
        c = np.asarray(center, dtype=np.float32)
        d2 = np.sum((a-c)**2, axis=1)
        return [ids[i] for i in np.flatnonzero(d2 <= radius*radius)]

    def all_pairs_near(self, positions: Dict[str, Coord], radius: float) -> List[Tuple[str, str]]:
        ids = sorted(positions)
        if len(ids) < 2:
            return []
        a = np.asarray([positions[i] for i in ids], dtype=np.float32)
        delta = a[:, None, :] - a[None, :, :]
        d2 = np.sum(delta*delta, axis=2)
        ii, jj = np.where(np.triu(d2 <= radius*radius, k=1))
        return [(ids[int(i)], ids[int(j)]) for i, j in zip(ii, jj)]
