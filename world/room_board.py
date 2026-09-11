"""Mutable environments (rooms/zones) that sims decorate and manage.

Style: Massive Manas / Sims — agents change theme + props inside POIs.
No LLM in geometry; decisions are discrete choices applied deterministically.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

THEME_CATALOG: Tuple[str, ...] = (
    "cyberpunk",
    "warm",
    "neon_garden",
    "loft",
    "studio",
)

PROP_CATALOG: Dict[str, Dict[str, Any]] = {
    "sofa": {"cost": 2.0, "label": "Sofa"},
    "plant": {"cost": 0.5, "label": "Plant"},
    "desk": {"cost": 1.5, "label": "Desk"},
    "neon_sign": {"cost": 1.0, "label": "Neon sign"},
    "counter": {"cost": 2.5, "label": "Counter"},
    "bed": {"cost": 2.0, "label": "Bed"},
    "bookshelf": {"cost": 1.5, "label": "Bookshelf"},
    "bar_stool": {"cost": 0.8, "label": "Bar stool"},
    "table": {"cost": 1.2, "label": "Table"},
    "poster": {"cost": 0.4, "label": "Poster"},
}

MAX_PROPS = 8
THEME_COST = 1.0


@dataclass
class RoomProp:
    prop_id: str
    kind: str
    x: float
    z: float
    rot: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RoomState:
    poi: str
    theme: str = "cyberpunk"
    props: List[RoomProp] = field(default_factory=list)
    layout_version: int = 0
    stewards: List[str] = field(default_factory=list)
    last_editor: str = ""
    last_edit_tick: int = -1

    def as_dict(self) -> dict:
        return {
            "poi": self.poi,
            "theme": self.theme,
            "props": [p.as_dict() for p in self.props],
            "layout_version": self.layout_version,
            "stewards": list(self.stewards),
            "last_editor": self.last_editor,
            "last_edit_tick": self.last_edit_tick,
            "prop_count": len(self.props),
        }


def _slot(index: int) -> Tuple[float, float, float]:
    """Deterministic furniture slots in normalized room coords (−0.35…0.35)."""
    slots = [
        (-0.28, -0.22, 0.0),
        (0.28, -0.22, 0.0),
        (-0.28, 0.18, 0.4),
        (0.28, 0.18, -0.4),
        (0.0, -0.05, 0.0),
        (-0.18, 0.0, 1.2),
        (0.18, 0.0, -1.2),
        (0.0, 0.28, 3.14),
    ]
    return slots[index % len(slots)]


class RoomBoard:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rooms: Dict[str, RoomState] = {}
        self.stats = {
            "themes_set": 0,
            "props_added": 0,
            "props_removed": 0,
            "edits": 0,
            "rejects": 0,
        }

    def seed_pois(self, pois: Sequence[str]) -> None:
        for poi in pois:
            self.ensure_room(poi)

    def ensure_room(self, poi: str) -> RoomState:
        if poi not in self.rooms:
            # Light default: plant + desk so rooms never look empty
            room = RoomState(poi=poi, theme="cyberpunk")
            for i, kind in enumerate(("plant", "desk")):
                x, z, rot = _slot(i)
                pid = self._prop_id(poi, kind, i)
                room.props.append(RoomProp(prop_id=pid, kind=kind, x=x, z=z, rot=rot))
            self.rooms[poi] = room
        return self.rooms[poi]

    def _prop_id(self, poi: str, kind: str, n: int) -> str:
        raw = hashlib.sha256(f"{self.seed}:{poi}:{kind}:{n}".encode()).hexdigest()[:10]
        return f"{kind}_{raw}"

    def choices_for(self, poi: str, money: float) -> List[str]:
        room = self.ensure_room(poi)
        out = ["skip_room"]
        for theme in THEME_CATALOG:
            if theme != room.theme and money + 1e-9 >= THEME_COST:
                out.append(f"set_theme_{theme}")
        if len(room.props) < MAX_PROPS:
            for kind, meta in PROP_CATALOG.items():
                if money + 1e-9 >= float(meta["cost"]):
                    out.append(f"add_prop_{kind}")
        # sorted(): un set di stringhe itera in un ordine dipendente da PYTHONHASHSEED
        # (randomizzato per processo), non dal seed della simulazione -> due run
        # identiche potevano produrre choices in ordine diverso, cambiare l'hash della
        # richiesta (rid) e quindi la scelta fallback deterministica. Bugfix
        # determinismo scoperto 2026-09-11 confrontando due run tick-by-tick.
        kinds_present = {p.kind for p in room.props}
        for kind in sorted(kinds_present):
            out.append(f"remove_prop_{kind}")
        return out

    def apply(
        self,
        *,
        tick: int,
        agent_id: str,
        poi: str,
        choice: str,
        runtime_money: float,
    ) -> Tuple[float, Optional[dict]]:
        if choice == "skip_room" or not choice:
            return runtime_money, None
        room = self.ensure_room(poi)
        if choice.startswith("set_theme_"):
            theme = choice[len("set_theme_") :]
            if theme not in THEME_CATALOG:
                self.stats["rejects"] += 1
                return runtime_money, {
                    "type": "room_reject",
                    "tick": tick,
                    "agent_id": agent_id,
                    "poi": poi,
                    "reason": "unknown_theme",
                    "choice": choice,
                }
            if runtime_money + 1e-9 < THEME_COST:
                self.stats["rejects"] += 1
                return runtime_money, {
                    "type": "room_reject",
                    "tick": tick,
                    "agent_id": agent_id,
                    "poi": poi,
                    "reason": "funds",
                    "choice": choice,
                }
            room.theme = theme
            room.layout_version += 1
            new_money = round(runtime_money - THEME_COST, 3)
            self._touch(room, agent_id, tick)
            self.stats["themes_set"] += 1
            self.stats["edits"] += 1
            return new_money, {
                "type": "room_apply",
                "tick": tick,
                "agent_id": agent_id,
                "poi": poi,
                "action": "set_theme",
                "theme": theme,
                "layout_version": room.layout_version,
                "room": room.as_dict(),
                "thought": f"Cambio look di {poi} → {theme}",
            }

        if choice.startswith("add_prop_"):
            kind = choice[len("add_prop_") :]
            meta = PROP_CATALOG.get(kind)
            if meta is None:
                self.stats["rejects"] += 1
                return runtime_money, {
                    "type": "room_reject",
                    "tick": tick,
                    "agent_id": agent_id,
                    "poi": poi,
                    "reason": "unknown_prop",
                    "choice": choice,
                }
            cost = float(meta["cost"])
            if len(room.props) >= MAX_PROPS:
                self.stats["rejects"] += 1
                return runtime_money, {
                    "type": "room_reject",
                    "tick": tick,
                    "agent_id": agent_id,
                    "poi": poi,
                    "reason": "full",
                    "choice": choice,
                }
            if runtime_money + 1e-9 < cost:
                self.stats["rejects"] += 1
                return runtime_money, {
                    "type": "room_reject",
                    "tick": tick,
                    "agent_id": agent_id,
                    "poi": poi,
                    "reason": "funds",
                    "choice": choice,
                }
            x, z, rot = _slot(len(room.props))
            pid = self._prop_id(poi, kind, len(room.props) + room.layout_version)
            room.props.append(RoomProp(prop_id=pid, kind=kind, x=x, z=z, rot=rot))
            room.layout_version += 1
            new_money = round(runtime_money - cost, 3)
            self._touch(room, agent_id, tick)
            self.stats["props_added"] += 1
            self.stats["edits"] += 1
            return new_money, {
                "type": "room_apply",
                "tick": tick,
                "agent_id": agent_id,
                "poi": poi,
                "action": "add_prop",
                "prop_kind": kind,
                "layout_version": room.layout_version,
                "room": room.as_dict(),
                "thought": f"Aggiungo {meta['label']} in {poi}",
            }

        if choice.startswith("remove_prop_"):
            kind = choice[len("remove_prop_") :]
            idx = next((i for i, p in enumerate(room.props) if p.kind == kind), -1)
            if idx < 0:
                self.stats["rejects"] += 1
                return runtime_money, {
                    "type": "room_reject",
                    "tick": tick,
                    "agent_id": agent_id,
                    "poi": poi,
                    "reason": "missing_prop",
                    "choice": choice,
                }
            removed = room.props.pop(idx)
            room.layout_version += 1
            self._touch(room, agent_id, tick)
            self.stats["props_removed"] += 1
            self.stats["edits"] += 1
            return runtime_money, {
                "type": "room_apply",
                "tick": tick,
                "agent_id": agent_id,
                "poi": poi,
                "action": "remove_prop",
                "prop_kind": removed.kind,
                "layout_version": room.layout_version,
                "room": room.as_dict(),
                "thought": f"Rimuovo {removed.kind} da {poi}",
            }

        self.stats["rejects"] += 1
        return runtime_money, {
            "type": "room_reject",
            "tick": tick,
            "agent_id": agent_id,
            "poi": poi,
            "reason": "unknown_choice",
            "choice": choice,
        }

    def _touch(self, room: RoomState, agent_id: str, tick: int) -> None:
        room.last_editor = agent_id
        room.last_edit_tick = tick
        if agent_id not in room.stewards:
            room.stewards.append(agent_id)

    def snapshot(self) -> dict:
        return {
            "rooms": {k: v.as_dict() for k, v in sorted(self.rooms.items())},
            "themes": list(THEME_CATALOG),
            "prop_catalog": {
                k: {"cost": v["cost"], "label": v["label"]} for k, v in PROP_CATALOG.items()
            },
            "stats": dict(self.stats),
        }

    def to_state(self) -> dict:
        return {
            "seed": self.seed,
            "rooms": {k: v.as_dict() for k, v in self.rooms.items()},
            "stats": dict(self.stats),
        }

    def load_state(self, state: dict) -> None:
        if not state:
            return
        self.seed = int(state.get("seed", self.seed))
        self.stats = dict(state.get("stats") or self.stats)
        self.rooms.clear()
        for poi, raw in (state.get("rooms") or {}).items():
            props = [
                RoomProp(
                    prop_id=str(p.get("prop_id") or f"{p.get('kind')}_{i}"),
                    kind=str(p.get("kind") or "plant"),
                    x=float(p.get("x", 0)),
                    z=float(p.get("z", 0)),
                    rot=float(p.get("rot", 0)),
                )
                for i, p in enumerate(raw.get("props") or [])
            ]
            self.rooms[str(poi)] = RoomState(
                poi=str(poi),
                theme=str(raw.get("theme") or "cyberpunk"),
                props=props,
                layout_version=int(raw.get("layout_version") or 0),
                stewards=list(raw.get("stewards") or []),
                last_editor=str(raw.get("last_editor") or ""),
                last_edit_tick=int(raw.get("last_edit_tick") or -1),
            )
