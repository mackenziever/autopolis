"""City self-construction driven by agent progress (no LLM in movement).

Agents work / study / unlock skills / change jobs → metrics rise →
deterministic blueprints unlock → new POIs cleared on the map.

An external consultant/tool can propose *additional* blueprints offline;
those are loaded from ``data/city_blueprints/*.json`` at engine start (not
mid-tick).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from config import Coord

# Built-in catalog (deterministic). Thresholds are cumulative city metrics.
DEFAULT_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "id": "library",
        "poi": "Library",
        "xy": [40, 22],
        "kind": "knowledge",
        "requires": {"skills_unlocked": 4, "lessons": 3},
        "unlocks": {"course_hint": "research_lab"},
        "description": "Biblioteca civica — studio collettivo",
    },
    {
        "id": "workshop",
        "poi": "Workshop",
        "xy": [18, 40],
        "kind": "industry",
        "requires": {"jobs_above_intern": 2, "money_total": 80.0},
        "unlocks": {"job_hint": "layout_designer"},
        "description": "Officina layout — produzione componenti UI in serie",
    },
    {
        "id": "lab",
        "poi": "Lab",
        "xy": [44, 36],
        "kind": "tech",
        "requires": {"skill_webgl": 2, "jobs_above_intern": 3},
        "unlocks": {"job_hint": "webgl_developer"},
        "description": "Laboratorio WebGL/3D — R&D cittadina",
    },
    {
        "id": "clinic",
        "poi": "Clinic",
        "xy": [8, 28],
        "kind": "care",
        "requires": {"skills_unlocked": 8, "social_events": 4},
        "unlocks": {},
        "description": "Clinica di quartiere — benessere",
    },
    {
        "id": "arena",
        "poi": "Arena",
        "xy": [36, 48],
        "kind": "culture",
        "requires": {"lessons": 12, "money_total": 200.0, "built": 2},
        "unlocks": {},
        "description": "Arena — eventi sociali e cultura",
    },
]


@dataclass
class CityMetrics:
    skills_unlocked: int = 0
    jobs_above_intern: int = 0
    money_total: float = 0.0
    lessons: int = 0
    social_events: int = 0
    skill_layout: int = 0
    skill_motion: int = 0
    skill_interaction: int = 0
    skill_webgl: int = 0
    built: int = 0
    reflections: int = 0
    exams_passed: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class BuiltPoi:
    blueprint_id: str
    poi: str
    xy: Coord
    tick: int
    kind: str = ""
    description: str = ""


@dataclass
class CityGrowthEngine:
    """Tracks progress and unlocks blueprints onto a CityMap."""

    seed: int
    blueprints: List[Dict[str, Any]] = field(default_factory=lambda: list(DEFAULT_BLUEPRINTS))
    metrics: CityMetrics = field(default_factory=CityMetrics)
    built: List[BuiltPoi] = field(default_factory=list)
    pending_events: List[dict] = field(default_factory=list)

    @classmethod
    def load(
        cls,
        seed: int,
        *,
        extra_dir: str | Path | None = "data/city_blueprints",
        enabled: bool = True,
    ) -> "CityGrowthEngine":
        bps = list(DEFAULT_BLUEPRINTS)
        if enabled and extra_dir:
            root = Path(extra_dir)
            if root.is_dir():
                for path in sorted(root.glob("*.json")):
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    items = data if isinstance(data, list) else data.get("blueprints") or [data]
                    for item in items:
                        if isinstance(item, dict) and item.get("id") and item.get("poi"):
                            # Externally-proposed blueprints tagged
                            item = dict(item)
                            item.setdefault("source", path.name)
                            bps.append(item)
        # Deduplicate by id (first wins = defaults)
        seen = set()
        unique = []
        for bp in bps:
            bid = str(bp["id"])
            if bid in seen:
                continue
            seen.add(bid)
            unique.append(bp)
        return cls(seed=seed, blueprints=unique)

    def observe_agents(self, agents: Sequence[Any]) -> None:
        """Recompute snapshot metrics from live AgentFSM list (deterministic)."""
        skills = set()
        jobs_hi = 0
        money = 0.0
        layout = motion = interaction = webgl = 0
        lesson_n = 0
        for a in agents:
            r = a.r
            for s in r.skills:
                skills.add(s)
                if s == "layout":
                    layout += 1
                elif s == "motion":
                    motion += 1
                elif s == "interaction":
                    interaction += 1
                elif s == "webgl":
                    webgl += 1
            if r.job != "intern":
                jobs_hi += 1
            money += float(r.money)
            improve = getattr(a.cog, "improve", None)
            if improve is not None:
                lesson_n += len(improve.lessons)
        self.metrics.skills_unlocked = len(skills - {"basic_literacy"})
        self.metrics.jobs_above_intern = jobs_hi
        self.metrics.money_total = round(money, 3)
        self.metrics.lessons = lesson_n
        self.metrics.skill_layout = layout
        self.metrics.skill_motion = motion
        self.metrics.skill_interaction = interaction
        self.metrics.skill_webgl = webgl
        self.metrics.built = len(self.built)

    def observe_events(self, events: Sequence[dict]) -> None:
        for e in events:
            t = e.get("type")
            if t == "social_decision":
                self.metrics.social_events += 1
            elif t == "reflection":
                self.metrics.reflections += 1
            elif t == "exam_result" and e.get("passed"):
                self.metrics.exams_passed += 1

    def _meets(self, requires: dict) -> bool:
        m = self.metrics.as_dict()
        for key, need in (requires or {}).items():
            if key == "built":
                have = len(self.built)
            else:
                have = m.get(key, 0)
            try:
                if float(have) < float(need):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    @staticmethod
    def _first_free_slot(city_map: Any, *, base: Coord) -> Coord:
        """Cerca a spirale attorno a `base` il primo punto a distanza Chebyshev
        >= MIN_POI_SPACING (7, coerente con agents/state_machine.py) da ogni POI
        gia' registrato. Deterministico: nessun RNG, solo distanza crescente."""
        pois = getattr(city_map, "pois", {}) or {}
        occupied = list(pois.values())

        def far_enough(cand: Coord) -> bool:
            return all(max(abs(cand[0] - ox), abs(cand[1] - oy)) >= 7 for ox, oy in occupied)

        if far_enough(base):
            return base
        for radius in range(1, 40):
            for dx in range(-radius, radius + 1):
                for dy in (-radius, radius):
                    cand = (base[0] + dx, base[1] + dy)
                    if far_enough(cand):
                        return cand
            for dy in range(-radius + 1, radius):
                for dx in (-radius, radius):
                    cand = (base[0] + dx, base[1] + dy)
                    if far_enough(cand):
                        return cand
        return base  # fallback estremo: mai raggiunto in pratica

    def try_build(self, tick: int, city_map: Any) -> List[dict]:
        """Unlock next eligible blueprint(s). At most one build per call (pace)."""
        built_ids = {b.blueprint_id for b in self.built}
        events: List[dict] = []
        for bp in self.blueprints:
            bid = str(bp["id"])
            if bid in built_ids:
                continue
            if not self._meets(bp.get("requires") or {}):
                continue
            poi = str(bp["poi"])
            xy_raw = bp.get("xy")
            if xy_raw:
                xy: Coord = (int(xy_raw[0]), int(xy_raw[1]))
            else:
                # Nessun xy esplicito nel blueprint: cerca il primo slot libero
                # (Chebyshev >= 7 da ogni POI esistente) invece di piazzare
                # sempre sul default [32,32] — due blueprint senza xy
                # finirebbero altrimenti sovrapposti (bug "edifici sovrapposti"
                # segnalato dall'utente per le rilocazioni, stessa classe qui).
                xy = self._first_free_slot(city_map, base=(32, 32))
            if hasattr(city_map, "register_poi"):
                city_map.register_poi(poi, xy)
            built = BuiltPoi(
                blueprint_id=bid,
                poi=poi,
                xy=xy,
                tick=tick,
                kind=str(bp.get("kind") or ""),
                description=str(bp.get("description") or ""),
            )
            self.built.append(built)
            self.metrics.built = len(self.built)
            ev = {
                "type": "city_build",
                "tick": tick,
                "blueprint_id": bid,
                "poi": poi,
                "xy": list(xy),
                "kind": built.kind,
                "description": built.description,
                "metrics": self.metrics.as_dict(),
                "thought": f"La città costruisce {poi}: progresso collettivo degli AGI-OS.",
            }
            events.append(ev)
            self.pending_events.append(ev)
            break  # one building per evaluation
        return events

    def step(self, tick: int, agents: Sequence[Any], events: Sequence[dict], city_map: Any) -> List[dict]:
        self.observe_events(events)
        self.observe_agents(agents)
        return self.try_build(tick, city_map)

    def snapshot(self) -> dict:
        return {
            "metrics": self.metrics.as_dict(),
            "built": [asdict(b) for b in self.built],
            "blueprints_total": len(self.blueprints),
            "blueprints_remaining": [
                bp["id"]
                for bp in self.blueprints
                if bp["id"] not in {b.blueprint_id for b in self.built}
            ],
            "next_candidates": self._next_candidates(),
        }

    def _next_candidates(self) -> List[dict]:
        built_ids = {b.blueprint_id for b in self.built}
        out = []
        for bp in self.blueprints:
            if bp["id"] in built_ids:
                continue
            req = bp.get("requires") or {}
            gaps = {}
            m = self.metrics.as_dict()
            for k, need in req.items():
                have = len(self.built) if k == "built" else m.get(k, 0)
                if float(have) < float(need):
                    gaps[k] = {"have": have, "need": need}
            out.append({"id": bp["id"], "poi": bp["poi"], "gaps": gaps, "ready": not gaps})
            if len(out) >= 5:
                break
        return out


def validate_blueprint(item: dict, city_map=None) -> Tuple[bool, str]:
    """`city_map` e' opzionale: i chiamanti (parse_blueprints_from_text(),
    scripts/apply_external_blueprint.py) validano il testo esterno PRIMA che
    una CityMap sia disponibile in quel contesto — senza il default 64x64,
    `city_map` era un nome mai definito nel modulo e ogni blueprint con `xy`
    valido faceva fallire la validazione con NameError (bug preesistente,
    mai esercitato prima della suite pytest completa)."""
    if not isinstance(item, dict):
        return False, "not_object"
    if not item.get("id") or not item.get("poi"):
        return False, "missing_id_or_poi"
    xy = item.get("xy")
    if not isinstance(xy, (list, tuple)) or len(xy) != 2:
        return False, "xy_must_be_[x,y]"
    try:
        x, y = int(xy[0]), int(xy[1])
    except (TypeError, ValueError):
        return False, "xy_not_int"
    if not (0 <= x < getattr(city_map, "width", 64) and 0 <= y < getattr(city_map, "height", 64)):
        return False, "xy_out_of_bounds_city"
    if "requires" in item and not isinstance(item["requires"], dict):
        return False, "requires_not_object"
    return True, "ok"


def parse_blueprints_from_text(text: str) -> List[dict]:
    """Extract JSON blueprint array/object from free-form external text."""
    text = text.strip()
    # Fenced block
    if "```" in text:
        parts = text.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                body = part
                if body.lstrip().startswith("json"):
                    body = body.lstrip()[4:]
                text = body.strip()
                break
    # Find first [ or {
    start_arr = text.find("[")
    start_obj = text.find("{")
    if start_arr < 0 and start_obj < 0:
        return []
    if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
        chunk = text[start_arr:]
        end = chunk.rfind("]")
        if end < 0:
            return []
        raw = chunk[: end + 1]
    else:
        chunk = text[start_obj:]
        end = chunk.rfind("}")
        if end < 0:
            return []
        raw = chunk[: end + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = data if isinstance(data, list) else data.get("blueprints") or [data]
    ok = []
    for item in items:
        valid, _ = validate_blueprint(item)
        if valid:
            ok.append(item)
    return ok
