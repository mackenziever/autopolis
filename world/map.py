"""CityMap: ostacoli + POI statici e dinamici (city growth).

La griglia città resta [0, width) x [0, height).
Attorno c'è una fascia wilderness (margin) sempre camminabile: gli agenti
possono uscire dalla città verso landmark esterni.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple, Iterable, List
import numpy as np
from config import POIS, WILDERNESS_LANDMARKS, Coord

@dataclass(frozen=True)
class MapSnapshot:
    width: int
    height: int
    blocked_cells: tuple[Coord, ...]
    pois: Dict[str, Coord]
    wilderness_margin: int = 0

class CityMap:
    def __init__(
        self,
        width: int,
        height: int,
        seed: int,
        obstacle_density: float = 0.08,
        wilderness_margin: int = 24,
    ):
        self.width, self.height = width, height
        self.margin = max(0, int(wilderness_margin))
        rng = np.random.default_rng(seed)
        self.blocked = rng.random((height, width)) < obstacle_density
        # Corridoi stradali principali sempre liberi.
        self.blocked[6, :] = False
        self.blocked[10, :] = False
        self.blocked[32, :] = False
        self.blocked[50, :] = False
        self.blocked[:, 6] = False
        self.blocked[:, 10] = False
        self.blocked[:, 32] = False
        self.blocked[:, 54] = False
        self.pois: Dict[str, Coord] = dict(POIS)
        # Libera POI e area 7x7 attorno a ciascuno.
        for x, y in self.pois.values():
            self._clear_around(x, y)
        # Landmark wilderness (fuori mappa città) — raggiungibili in EXPLORING
        for name, xy in WILDERNESS_LANDMARKS.items():
            self.pois[name] = (int(xy[0]), int(xy[1]))

    def _clear_around(self, x: int, y: int, radius: int = 3) -> None:
        x0, x1 = max(0, x - radius), min(self.width, x + radius + 1)
        y0, y1 = max(0, y - radius), min(self.height, y + radius + 1)
        self.blocked[y0:y1, x0:x1] = False

    def register_poi(self, name: str, xy: Coord) -> None:
        """Registra un POI costruito (city growth). Idempotente sul nome."""
        x, y = int(xy[0]), int(xy[1])
        if not self.in_city((x, y)):
            return
        self.pois[name] = (x, y)
        self._clear_around(x, y)

    def in_city(self, c: Coord) -> bool:
        x, y = int(c[0]), int(c[1])
        return 0 <= x < self.width and 0 <= y < self.height

    def in_bounds(self, c: Coord) -> bool:
        """Città + wilderness margin."""
        x, y = int(c[0]), int(c[1])
        m = self.margin
        return -m <= x < self.width + m and -m <= y < self.height + m

    def walkable(self, c: Coord) -> bool:
        x, y = int(c[0]), int(c[1])
        if not self.in_bounds((x, y)):
            return False
        if self.in_city((x, y)):
            return not bool(self.blocked[y, x])
        return True  # wilderness aperta

    def neighbors(self, c: Coord, diagonal: bool = False) -> Iterable[Coord]:
        x, y = int(c[0]), int(c[1])
        dirs = [(1,0), (-1,0), (0,1), (0,-1)]
        if diagonal:
            dirs += [(1,1), (1,-1), (-1,1), (-1,-1)]
        for dx, dy in dirs:
            n = (x+dx, y+dy)
            if self.walkable(n):
                yield n

    def slot_near(self, poi_name: str, agent_number: int, radius: int = 3) -> Coord:
        """Assegna uno slot stabile attorno a un POI per evitare 50 agenti su una cella."""
        if poi_name not in self.pois:
            bx, by = self.pois.get("Home", (6, 6))
        else:
            bx, by = self.pois[poi_name]
        if str(poi_name).startswith("Wild_"):
            ox = (agent_number % 5) - 2
            oy = ((agent_number // 5) % 5) - 2
            cand = (bx + ox, by + oy)
            return cand if self.walkable(cand) else (bx, by)
        offsets: List[Coord] = []
        for r in range(radius + 1):
            for dy in range(-r, r+1):
                for dx in range(-r, r+1):
                    if max(abs(dx), abs(dy)) == r:
                        offsets.append((dx, dy))
        for j in range(len(offsets)):
            dx, dy = offsets[(agent_number + j) % len(offsets)]
            c = (bx+dx, by+dy)
            if self.walkable(c):
                return c
        return (bx, by)

    def snapshot(self) -> MapSnapshot:
        ys, xs = np.where(self.blocked)
        return MapSnapshot(
            self.width,
            self.height,
            tuple((int(x), int(y)) for x, y in zip(xs, ys)),
            dict(self.pois),
            wilderness_margin=self.margin,
        )
