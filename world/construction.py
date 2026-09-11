"""Agent-funded city construction (escrow) — parity+ vs Civitas reel.

An AGI-OS can propose a build with its own money (escrow). Others contribute.
After funding + build_days, the POI appears on the map. No LLM in A*/move.

Better than threshold-only growth: intentional founder + collective funding +
attendance tracking when agents socialize at the new site.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from config import Coord

# Tuned to Civitas wage scale (~1–4 / tick unit). Reel used 400 in a richer economy;
# here Cafe is founder-led with escrow + peer contributions over ~2–3 sim days.
BUILD_CATALOG: Dict[str, Dict[str, Any]] = {
    "cafe": {
        "poi": "AgentCafe",
        "xy": (46, 46),
        "cost": 40.0,
        "founder_min": 12.0,
        "build_days": 2,
        "kind": "hospitality",
        "description": "Cafe fondato da un agente (escrow + contributi)",
    },
    "tower_lounge": {
        "poi": "TowerLounge",
        "xy": (28, 18),
        "cost": 55.0,
        "founder_min": 18.0,
        "build_days": 3,
        "kind": "culture",
        "description": "Lounge su piano torre — arredo collettivo",
    },
    "market_stall": {
        "poi": "MarketStall",
        "xy": (34, 10),
        "cost": 25.0,
        "founder_min": 8.0,
        "build_days": 1,
        "kind": "commerce",
        "description": "Bancarella agente al Market",
    },
}


# Rilocazione POI esistenti (stile reel: due agenti pagano per spostare un cafe').
RELOCATE_BASE_FEE = 20.0
RELOCATE_WAGE_PER_DAY = 2.0
RELOCATE_CREW_NEEDED = 2
RELOCATE_DAYS_TOTAL = 2
RELOCATE_MAX_DISTANCE = 30  # celle, in norma Chebyshev


@dataclass
class RelocateProject:
    project_id: str
    poi: str
    from_xy: Coord
    to_xy: Coord
    proposer_id: str
    crew_needed: int = RELOCATE_CREW_NEEDED
    wage_per_day: float = RELOCATE_WAGE_PER_DAY
    days_total: int = RELOCATE_DAYS_TOTAL
    days_remaining: int = RELOCATE_DAYS_TOTAL
    escrow: float = 0.0
    day_started: int = 0
    last_paid_day: int = -1
    crew: List[str] = field(default_factory=list)
    status: str = "relocating"  # relocating | complete | failed | cancelled

    def as_dict(self) -> dict:
        d = asdict(self)
        d["from_xy"] = list(self.from_xy)
        d["to_xy"] = list(self.to_xy)
        return d


@dataclass
class ConstructionProject:
    project_id: str
    kind: str
    poi: str
    xy: Coord
    founder_id: str
    cost: float
    escrow: float = 0.0
    build_days: int = 2
    day_started: int = 0
    status: str = "funding"  # funding | building | complete | cancelled
    contributors: Dict[str, float] = field(default_factory=dict)
    visitors: List[str] = field(default_factory=list)
    completed_tick: int = -1
    description: str = ""

    def funded(self) -> bool:
        return self.escrow + 1e-9 >= self.cost

    def as_dict(self) -> dict:
        d = asdict(self)
        d["xy"] = list(self.xy)
        d["funded"] = self.funded()
        d["remaining"] = max(0.0, round(self.cost - self.escrow, 3))
        return d


class ConstructionBoard:
    def __init__(self, seed: int = 42, day_length: int = 600):
        self.seed = seed
        self.day_length = day_length
        self.projects: Dict[str, ConstructionProject] = {}
        self.completed_pois: List[str] = []
        self.relocations: Dict[str, RelocateProject] = {}
        self.stats = {
            "proposed": 0,
            "contributions": 0,
            "completed": 0,
            "escrow_total": 0.0,
            "attendance_peak": 0,
            "relocations_proposed": 0,
            "relocations_completed": 0,
            "relocations_failed": 0,
        }

    def open_projects(self) -> List[ConstructionProject]:
        return [p for p in self.projects.values() if p.status in ("funding", "building")]

    def active_destinations(self) -> List[str]:
        """POI targets that pull social traffic (open sites + newly completed)."""
        out = []
        for p in self.projects.values():
            if p.status == "building" or (
                p.status == "complete" and p.poi not in out
            ):
                out.append(p.poi)
            elif p.status == "funding":
                # Site known before complete — still attract helpers
                out.append(p.poi)
        for poi in self.completed_pois:
            if poi not in out:
                out.append(poi)
        return out

    def _pid(self, founder: str, kind: str, day: int) -> str:
        raw = f"{self.seed}:{founder}:{kind}:{day}"
        return "build_" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def can_propose(self, agent_id: str, kind: str, money: float) -> Tuple[bool, str]:
        if kind not in BUILD_CATALOG:
            return False, "unknown_kind"
        if any(p.kind == kind and p.status != "complete" for p in self.projects.values()):
            return False, "kind_already_open"
        if any(p.poi == BUILD_CATALOG[kind]["poi"] for p in self.projects.values() if p.status == "complete"):
            return False, "already_built"
        need = float(BUILD_CATALOG[kind]["founder_min"])
        if money + 1e-9 < need:
            return False, "insufficient_funds"
        return True, "ok"

    def propose(
        self,
        *,
        tick: int,
        day: int,
        founder_id: str,
        kind: str,
        runtime_money: float,
    ) -> Tuple[Optional[ConstructionProject], float, Optional[dict]]:
        """Deduct founder_min into escrow. Returns (project, new_money, event)."""
        ok, reason = self.can_propose(founder_id, kind, runtime_money)
        if not ok:
            return None, runtime_money, {
                "type": "build_reject",
                "tick": tick,
                "agent_id": founder_id,
                "kind": kind,
                "reason": reason,
            }
        spec = BUILD_CATALOG[kind]
        deposit = float(spec["founder_min"])
        xy = (int(spec["xy"][0]), int(spec["xy"][1]))
        pid = self._pid(founder_id, kind, day)
        proj = ConstructionProject(
            project_id=pid,
            kind=kind,
            poi=str(spec["poi"]),
            xy=xy,
            founder_id=founder_id,
            cost=float(spec["cost"]),
            escrow=deposit,
            build_days=int(spec["build_days"]),
            day_started=day,
            status="funding",
            contributors={founder_id: deposit},
            description=str(spec.get("description") or ""),
        )
        if proj.funded():
            proj.status = "building"
        self.projects[pid] = proj
        self.stats["proposed"] += 1
        self.stats["escrow_total"] += deposit
        new_money = round(runtime_money - deposit, 3)
        ev = {
            "type": "build_propose",
            "tick": tick,
            "agent_id": founder_id,
            "project_id": pid,
            "kind": kind,
            "poi": proj.poi,
            "xy": list(xy),
            "escrow": deposit,
            "cost": proj.cost,
            "thought": f"Metto {deposit} in escrow per costruire {proj.poi}. Nessuno me l'ha ordinato.",
        }
        return proj, new_money, ev

    def contribute(
        self,
        *,
        tick: int,
        agent_id: str,
        amount: float,
        runtime_money: float,
        project_id: str | None = None,
    ) -> Tuple[float, Optional[dict]]:
        amount = round(min(amount, runtime_money), 3)
        if amount <= 0:
            return runtime_money, None
        open_ = self.open_projects()
        if not open_:
            return runtime_money, None
        if project_id and project_id in self.projects:
            proj = self.projects[project_id]
        else:
            # Prefer underfunded, else first building
            funding = [p for p in open_ if p.status == "funding"]
            proj = funding[0] if funding else open_[0]
        if proj.status == "complete":
            return runtime_money, None
        need = max(0.0, proj.cost - proj.escrow)
        put = round(min(amount, need if need > 0 else amount), 3)
        if put <= 0 and proj.status == "funding":
            return runtime_money, None
        if put <= 0:
            put = round(min(amount, 1.0), 3)  # symbolic help while building
        proj.escrow = round(proj.escrow + put, 3)
        proj.contributors[agent_id] = round(proj.contributors.get(agent_id, 0.0) + put, 3)
        self.stats["contributions"] += 1
        self.stats["escrow_total"] += put
        if proj.status == "funding" and proj.funded():
            proj.status = "building"
        new_money = round(runtime_money - put, 3)
        return new_money, {
            "type": "build_contribute",
            "tick": tick,
            "agent_id": agent_id,
            "project_id": proj.project_id,
            "poi": proj.poi,
            "amount": put,
            "escrow": proj.escrow,
            "status": proj.status,
            "thought": f"Contribuisco {put} a {proj.poi} (escrow={proj.escrow}/{proj.cost}).",
        }

    def tick_day(self, day: int, tick: int, city_map: Any) -> List[dict]:
        """Advance building projects; complete when funded and days elapsed."""
        events: List[dict] = []
        for proj in list(self.projects.values()):
            if proj.status != "building":
                continue
            if day - proj.day_started < proj.build_days:
                continue
            if not proj.funded():
                continue
            if hasattr(city_map, "register_poi"):
                city_map.register_poi(proj.poi, proj.xy)
            proj.status = "complete"
            proj.completed_tick = tick
            if proj.poi not in self.completed_pois:
                self.completed_pois.append(proj.poi)
            self.stats["completed"] += 1
            events.append(
                {
                    "type": "city_build",
                    "tick": tick,
                    "source": "agent_escrow",
                    "blueprint_id": proj.kind,
                    "project_id": proj.project_id,
                    "poi": proj.poi,
                    "xy": list(proj.xy),
                    "founder_id": proj.founder_id,
                    "escrow": proj.escrow,
                    "contributors": dict(proj.contributors),
                    "visitors": list(proj.visitors),
                    "description": proj.description,
                    "thought": (
                        f"{proj.poi} aperto: fondatore {proj.founder_id}, "
                        f"{len(proj.contributors)} contributori, escrow={proj.escrow}."
                    ),
                }
            )
        for proj in sorted(self.relocations.values(), key=lambda r: r.project_id):
            if proj.status != "relocating":
                continue
            if day <= proj.day_started or day <= proj.last_paid_day:
                continue
            proj.last_paid_day = day
            for worker_id in sorted(proj.crew):
                if proj.escrow < proj.wage_per_day:
                    break
                proj.escrow = round(proj.escrow - proj.wage_per_day, 3)
                events.append(
                    {
                        "type": "relocate_wage_paid",
                        "tick": tick,
                        "agent_id": worker_id,
                        "project_id": proj.project_id,
                        "amount": proj.wage_per_day,
                    }
                )
            proj.days_remaining -= 1
            if proj.days_remaining > 0:
                continue
            if len(proj.crew) >= proj.crew_needed and hasattr(city_map, "register_poi"):
                city_map.register_poi(proj.poi, proj.to_xy)
                proj.status = "complete"
                self.stats["relocations_completed"] += 1
                events.append(
                    {
                        "type": "relocate_completed",
                        "tick": tick,
                        "poi": proj.poi,
                        "project_id": proj.project_id,
                        "to": list(proj.to_xy),
                        "crew": sorted(proj.crew),
                        "thought": f"{proj.poi} ora e' in {proj.to_xy}. Manodopera pagata: {sorted(proj.crew)}.",
                    }
                )
            else:
                proj.status = "failed"
                self.stats["relocations_failed"] += 1
                events.append(
                    {
                        "type": "relocate_failed",
                        "tick": tick,
                        "poi": proj.poi,
                        "project_id": proj.project_id,
                        "reason": "crew_incomplete",
                    }
                )
        return events

    # -- relocation (Stage 7: sposta un POI gia' costruito) --------------------
    def _rpid(self, proposer: str, poi: str, day: int) -> str:
        raw = f"{self.seed}:relocate:{proposer}:{poi}:{day}"
        return "reloc_" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def open_relocations(self) -> List[RelocateProject]:
        return sorted(
            (r for r in self.relocations.values() if r.status == "relocating"),
            key=lambda r: r.project_id,
        )

    def can_propose_relocate(
        self, agent_id: str, poi: str, to_xy: Coord, money: float, city_map: Any
    ) -> Tuple[bool, str]:
        if poi not in self.completed_pois:
            return False, "poi_not_relocatable"
        if any(r.poi == poi and r.status == "relocating" for r in self.relocations.values()):
            return False, "already_relocating"
        pois = getattr(city_map, "pois", {}) or {}
        from_xy = pois.get(poi)
        if from_xy is None:
            return False, "poi_unknown_to_map"
        if hasattr(city_map, "walkable") and not city_map.walkable(tuple(to_xy)):
            return False, "target_blocked"
        dist = max(abs(int(to_xy[0]) - from_xy[0]), abs(int(to_xy[1]) - from_xy[1]))
        if dist > RELOCATE_MAX_DISTANCE:
            return False, "too_far"
        total_cost = RELOCATE_BASE_FEE + RELOCATE_WAGE_PER_DAY * RELOCATE_CREW_NEEDED * RELOCATE_DAYS_TOTAL
        if money + 1e-9 < total_cost:
            return False, "insufficient_funds"
        return True, "ok"

    def propose_relocate(
        self,
        *,
        tick: int,
        day: int,
        proposer_id: str,
        poi: str,
        to_xy: Coord,
        runtime_money: float,
        city_map: Any,
    ) -> Tuple[Optional[RelocateProject], float, Optional[dict]]:
        ok, reason = self.can_propose_relocate(proposer_id, poi, to_xy, runtime_money, city_map)
        if not ok:
            return None, runtime_money, {
                "type": "relocate_reject",
                "tick": tick,
                "agent_id": proposer_id,
                "poi": poi,
                "reason": reason,
            }
        from_xy = tuple(int(v) for v in city_map.pois[poi])
        to_xy = (int(to_xy[0]), int(to_xy[1]))
        total_cost = RELOCATE_BASE_FEE + RELOCATE_WAGE_PER_DAY * RELOCATE_CREW_NEEDED * RELOCATE_DAYS_TOTAL
        pid = self._rpid(proposer_id, poi, day)
        proj = RelocateProject(
            project_id=pid,
            poi=poi,
            from_xy=from_xy,
            to_xy=to_xy,
            proposer_id=proposer_id,
            escrow=total_cost,
            day_started=day,
        )
        self.relocations[pid] = proj
        self.stats["relocations_proposed"] += 1
        new_money = round(runtime_money - total_cost, 3)
        ev = {
            "type": "relocate_proposed",
            "tick": tick,
            "agent_id": proposer_id,
            "project_id": pid,
            "poi": poi,
            "from": list(from_xy),
            "to": list(to_xy),
            "escrow": total_cost,
            "thought": f"Pago {total_cost} per spostare {poi} da {from_xy} a {to_xy}.",
        }
        return proj, new_money, ev

    def join_crew(
        self, *, tick: int, agent_id: str, project_id: Optional[str] = None
    ) -> Optional[dict]:
        open_ = self.open_relocations()
        if not open_:
            return None
        proj = self.relocations.get(project_id) if project_id else None
        if proj is None or proj.status != "relocating":
            proj = open_[0]
        if agent_id in proj.crew or len(proj.crew) >= proj.crew_needed:
            return None
        proj.crew.append(agent_id)
        return {
            "type": "relocate_crew_joined",
            "tick": tick,
            "agent_id": agent_id,
            "project_id": proj.project_id,
            "poi": proj.poi,
        }

    def record_visit(self, poi: str, agent_id: str) -> None:
        for proj in self.projects.values():
            if proj.poi != poi:
                continue
            if agent_id not in proj.visitors:
                proj.visitors.append(agent_id)
            peak = len(proj.visitors)
            if peak > self.stats["attendance_peak"]:
                self.stats["attendance_peak"] = peak

    def suggest_social_poi(self, agent_id: str, tick: int, fallback: str = "Plaza") -> str:
        dests = self.active_destinations()
        if not dests:
            return fallback
        raw = hashlib.sha256(f"{self.seed}:{tick // 30}:{agent_id}".encode()).digest()
        # ~60% pull to agent-built sites when available
        if raw[0] < 154:
            return dests[raw[1] % len(dests)]
        return fallback

    def to_state(self) -> dict:
        """Stato grezzo per checkpoint (round-trip fedele, non il display snapshot())."""
        return {
            "projects": {pid: asdict(p) for pid, p in self.projects.items()},
            "completed_pois": list(self.completed_pois),
            "relocations": {rid: asdict(r) for rid, r in self.relocations.items()},
            "stats": dict(self.stats),
        }

    def load_state(self, state: dict) -> None:
        self.projects = {
            pid: ConstructionProject(**{**p, "xy": tuple(p["xy"])})
            for pid, p in (state.get("projects") or {}).items()
        }
        self.completed_pois = list(state.get("completed_pois") or [])
        self.relocations = {
            rid: RelocateProject(
                **{
                    **r,
                    "from_xy": tuple(r["from_xy"]),
                    "to_xy": tuple(r["to_xy"]),
                    "crew": list(r.get("crew") or []),
                }
            )
            for rid, r in (state.get("relocations") or {}).items()
        }
        self.stats.update(state.get("stats") or {})

    def snapshot(self) -> dict:
        return {
            "projects": [p.as_dict() for p in self.projects.values()],
            "completed_pois": list(self.completed_pois),
            "relocations": [r.as_dict() for r in self.relocations.values()],
            "stats": dict(self.stats),
            "catalog": {
                k: {
                    "poi": v["poi"],
                    "cost": v["cost"],
                    "founder_min": v["founder_min"],
                    "build_days": v["build_days"],
                }
                for k, v in BUILD_CATALOG.items()
            },
        }
