"""FSM autorevole. Gli step ordinari non eseguono chiamate LLM.

Decisioni FreeLLM/Alveare solo su eventi rari: reflect giornaliero, career,
study focus, social stance, build escrow — fuori dal hot-path movimento.
"""
from __future__ import annotations
import hashlib
from typing import List, Set

from agents.cognitive import AgentCognitiveEngine
from agents.models import AgentRuntime, AgentState
from agents.research import ResearchLoop
from config import COURSES, WILDERNESS_LANDMARKS
from engine.spatial import SpatialService
from metrics.collector import GLOBAL_COLLECTOR
from world.construction import BUILD_CATALOG
from world.economy import LaborMarket
from world.governance import PROPOSAL_CATALOG

# Distanza minima (Chebyshev) fra un nuovo bersaglio di rilocazione e ogni
# altro POI: >= 2*radius+1 di world.map.CityMap._clear_around (radius=3) per
# garantire che le due aree 7x7 liberate attorno agli edifici non si tocchino.
MIN_POI_SPACING = 7

TARGET = {
    AgentState.IDLE: "Home",
    AgentState.COMMUTING: "Office",
    AgentState.WORKING: "Office",
    AgentState.ATTENDING_CLASS: "Aula_101",
    AgentState.EXPLORING: "Wild_North",
    AgentState.SOCIALIZING: "Plaza",
    AgentState.EATING: "Cafe",
    AgentState.REST: "Home",
}
MOVING_STATES = {
    AgentState.COMMUTING,
    AgentState.ATTENDING_CLASS,
    AgentState.EXPLORING,
    AgentState.SOCIALIZING,
    AgentState.EATING,
}


class AgentFSM:
    def __init__(
        self,
        runtime: AgentRuntime,
        cognitive: AgentCognitiveEngine,
        spatial: SpatialService,
        economy: LaborMarket,
        day_length: int,
        study_required: int,
        paperclip_board=None,
        construction=None,
        governance=None,
        rooms=None,
        research: ResearchLoop | None = None,
    ):
        self.r, self.cog, self.spatial, self.economy = runtime, cognitive, spatial, economy
        self.day_length, self.study_required = day_length, study_required
        self.board = paperclip_board
        self.construction = construction
        self.governance = governance
        self.rooms = rooms
        self.research = research

    def _paperclip_checkout(self, tick: int, day: int, kind: str):
        if self.board is None:
            return None
        issue = self.board.find_issue(self.r.agent_id, day, kind)
        if issue is not None and issue.status == "todo":
            self.board.checkout(self.r.agent_id, issue.id, tick)
        return issue

    def _paperclip_complete(self, tick: int, day: int, kind: str, result: str):
        if self.board is None:
            return
        issue = self.board.find_issue(self.r.agent_id, day, kind)
        if issue is not None and issue.status != "done":
            self.board.complete(issue.id, result, tick)

    def _goal(self):
        return self.spatial.map.slot_near(self.r.target_poi, self.r.number, 3)

    def transition(self, tick: int, new_state: AgentState) -> List[dict]:
        if new_state == self.r.state:
            return []
        old = self.r.state
        self.r.previous_state = old
        self.r.state = new_state
        self.r.target_poi = TARGET[new_state]
        if new_state == AgentState.ATTENDING_CLASS:
            course = self.r.course_id()
            self.r.target_poi = COURSES[course][0]
        if new_state == AgentState.SOCIALIZING and self.construction is not None:
            self.r.target_poi = self.construction.suggest_social_poi(
                self.r.agent_id, tick, fallback="Plaza"
            )
        if new_state == AgentState.EATING and self.construction is not None:
            if "AgentCafe" in getattr(self.spatial.map, "pois", {}):
                self.r.target_poi = "AgentCafe"
        if new_state == AgentState.EXPLORING:
            names = sorted(WILDERNESS_LANDMARKS.keys())
            pick = names[(self.r.number + tick) % len(names)]
            self.r.target_poi = pick
            self.r.last_thought = f"Esco dalla città verso {pick}."
        self.r.path = self.spatial.astar(self.r.position, self._goal())
        if new_state != AgentState.EXPLORING:
            self.r.last_thought = f"Passo da {old} a {new_state} secondo piano e bisogni."
        return [
            {
                "type": "state_transition",
                "tick": tick,
                "agent_id": self.r.agent_id,
                "from": str(old),
                "to": str(new_state),
                "target": self.r.target_poi,
                "thought": self.r.last_thought,
            }
        ]

    def _deterministic_relocate_target(self, poi: str):
        """Bersaglio di rilocazione deterministico: funzione pura di poi/agent_id,
        nessun RNG runtime — stesso input, stesso output ad ogni replay.

        Bugfix (2026-09-11, "edifici sovrapposti" segnalato dall'utente in
        produzione): `walkable()` da solo NON basta a evitare un altro POI —
        `register_poi()`/`_clear_around()` liberano l'area 7x7 attorno a ogni
        edificio (cosi' gli agenti possono raggiungerlo), quindi la piastrella
        esatta di un POI esistente risulta "walkable". Serve un controllo
        esplicito di distanza minima da OGNI altro POI registrato, non solo
        dagli ostacoli di terreno.
        """
        city_map = self.spatial.map
        from_xy = city_map.pois.get(poi)
        if from_xy is None:
            return None
        occupied = [xy for name, xy in city_map.pois.items() if name != poi]
        raw = hashlib.sha256(f"relocate:{poi}:{self.r.agent_id}".encode()).digest()
        for i in range(len(raw) - 1):
            dx = (raw[i] % 21) - 10
            dy = (raw[i + 1] % 21) - 10
            cand = (from_xy[0] + dx, from_xy[1] + dy)
            if not city_map.in_bounds(cand) or not city_map.walkable(cand):
                continue
            if any(
                max(abs(cand[0] - ox), abs(cand[1] - oy)) < MIN_POI_SPACING
                for ox, oy in occupied
            ):
                # Telemetria (consiglio esterno, 2026-09-11, "5. Telemetry
                # end-to-end"): conta ogni candidato scartato per spacing, cosi'
                # una regressione sul bug "edifici sovrapposti" (segnalato in
                # produzione) si vede subito come un salto anomalo su /health
                # invece di dover aspettare un altro report visivo dell'utente.
                GLOBAL_COLLECTOR.inc("civitas_building_relocation_conflicts_total")
                continue
            return cand
        return None

    def _joinable_relocation_ids(self) -> List[str]:
        if self.construction is None:
            return []
        return [
            r.project_id
            for r in self.construction.open_relocations()
            if self.r.agent_id not in r.crew and len(r.crew) < r.crew_needed
        ]

    async def _maybe_build(self, tick: int, day: int, events: List[dict]) -> None:
        if self.construction is None:
            return
        if self.r.build_decided_day == day:
            return
        self.r.build_decided_day = day
        open_kinds = [p.kind for p in self.construction.open_projects()]
        can_propose = []
        for kind in BUILD_CATALOG:
            ok, _ = self.construction.can_propose(self.r.agent_id, kind, self.r.money)
            if ok:
                can_propose.append(kind)
        relocating_pois = {r.poi for r in self.construction.relocations.values() if r.status == "relocating"}
        can_relocate = [
            poi for poi in self.construction.completed_pois if poi not in relocating_pois
        ][:3]
        can_join_crew_ids = self._joinable_relocation_ids()
        if not open_kinds and not can_propose and not can_relocate and not can_join_crew_ids:
            return
        self._paperclip_checkout(tick, day, "build")
        decision = await self.cog.decide_build(
            tick,
            open_kinds=open_kinds,
            can_propose=can_propose,
            can_relocate=can_relocate,
            can_join_crew_ids=can_join_crew_ids,
        )
        choice = decision["choice"]
        self._paperclip_complete(tick, day, "build", decision.get("thought", choice))
        events.append(
            {
                "type": "build_decision",
                "tick": tick,
                "agent_id": self.r.agent_id,
                "choice": choice,
                "thought": decision["thought"],
                "confidence": decision.get("confidence", 0.0),
                "money": self.r.money,
            }
        )
        if choice.startswith("propose_relocate_"):
            poi = choice[len("propose_relocate_") :]
            to_xy = self._deterministic_relocate_target(poi)
            if to_xy is not None:
                _proj, new_money, ev = self.construction.propose_relocate(
                    tick=tick,
                    day=day,
                    proposer_id=self.r.agent_id,
                    poi=poi,
                    to_xy=to_xy,
                    runtime_money=self.r.money,
                    city_map=self.spatial.map,
                )
                self.r.money = new_money
                if ev:
                    events.append(ev)
        elif choice.startswith("join_crew_"):
            project_id = choice[len("join_crew_") :]
            ev = self.construction.join_crew(
                tick=tick, agent_id=self.r.agent_id, project_id=project_id
            )
            if ev:
                events.append(ev)
        elif choice.startswith("propose_"):
            kind = choice[len("propose_") :]
            _proj, new_money, ev = self.construction.propose(
                tick=tick,
                day=day,
                founder_id=self.r.agent_id,
                kind=kind,
                runtime_money=self.r.money,
            )
            self.r.money = new_money
            if ev:
                events.append(ev)
        elif choice == "contribute":
            amount = max(1.0, round(self.r.money * 0.15, 3))
            new_money, ev = self.construction.contribute(
                tick=tick,
                agent_id=self.r.agent_id,
                amount=amount,
                runtime_money=self.r.money,
            )
            self.r.money = new_money
            if ev:
                events.append(ev)

    async def _maybe_room(self, tick: int, day: int, events: List[dict]) -> None:
        """Sim gestisce l'ambiente del POI corrente (tema + arredi)."""
        if self.rooms is None:
            return
        if self.r.room_decided_day == day:
            return
        poi = self.r.target_poi or "Home"
        choices = self.rooms.choices_for(poi, self.r.money)
        # Solo skip → niente LLM
        if len(choices) <= 1:
            self.r.room_decided_day = day
            return
        self.r.room_decided_day = day
        room = self.rooms.ensure_room(poi)
        self._paperclip_checkout(tick, day, "room")
        decision = await self.cog.decide_room(
            tick,
            poi=poi,
            choices=choices,
            room_summary={
                "theme": room.theme,
                "prop_count": len(room.props),
                "props": [p.kind for p in room.props],
                "stewards": list(room.stewards[-3:]),
            },
        )
        choice = decision["choice"]
        self._paperclip_complete(tick, day, "room", decision.get("thought", choice))
        events.append(
            {
                "type": "room_decision",
                "tick": tick,
                "agent_id": self.r.agent_id,
                "poi": poi,
                "choice": choice,
                "thought": decision["thought"],
                "confidence": decision.get("confidence", 0.0),
                "money": self.r.money,
            }
        )
        new_money, ev = self.rooms.apply(
            tick=tick,
            agent_id=self.r.agent_id,
            poi=poi,
            choice=choice,
            runtime_money=self.r.money,
        )
        self.r.money = new_money
        if ev:
            events.append(ev)

    async def _maybe_govern(self, tick: int, day: int, events: List[dict]) -> None:
        if self.governance is None:
            return
        if self.r.governance_decided_day == day:
            return
        self.r.governance_decided_day = day
        can_propose_kinds = [
            k
            for k in PROPOSAL_CATALOG
            if self.governance.can_propose(self.r.agent_id, k, self.r.money)[0]
        ]
        open_proposals = self.governance.open_proposals()
        has_unvoted = any(self.r.agent_id not in p.votes for p in open_proposals)
        open_kinds = [p.kind for p in open_proposals]
        if not can_propose_kinds and not has_unvoted:
            return
        self._paperclip_checkout(tick, day, "governance")
        decision = await self.cog.decide_governance(
            tick,
            can_propose_kinds=can_propose_kinds,
            has_unvoted=has_unvoted,
            open_kinds=open_kinds,
        )
        choice = decision["choice"]
        self._paperclip_complete(tick, day, "governance", decision.get("thought", choice))
        events.append(
            {
                "type": "governance_decision",
                "tick": tick,
                "agent_id": self.r.agent_id,
                "choice": choice,
                "thought": decision["thought"],
                "confidence": decision.get("confidence", 0.0),
                "money": self.r.money,
            }
        )
        if choice.startswith("propose_"):
            kind = choice[len("propose_") :]
            _prop, new_money, ev = self.governance.propose(
                tick=tick,
                day=day,
                proposer_id=self.r.agent_id,
                kind=kind,
                runtime_money=self.r.money,
            )
            self.r.money = new_money
            if ev:
                events.append(ev)
        elif choice in ("vote_yes", "vote_no", "vote_abstain") and open_proposals:
            target = next((p for p in open_proposals if self.r.agent_id not in p.votes), None)
            if target is not None:
                vote = choice[len("vote_") :]
                ev = self.governance.cast_vote(
                    tick=tick,
                    proposal_id=target.proposal_id,
                    voter_id=self.r.agent_id,
                    vote=vote,
                )
                if ev:
                    events.append(ev)

    async def step(self, tick: int, scheduled: AgentState, reserved: Set[tuple]) -> List[dict]:
        day = tick // self.day_length
        state = scheduled
        if self.r.energy < 12:
            state = AgentState.REST
        elif self.r.hunger > 78 and scheduled not in (
            AgentState.REST,
            AgentState.ATTENDING_CLASS,
        ):
            state = AgentState.EATING
        events = self.transition(tick, state)

        if self.r.state in MOVING_STATES:
            goal = self._goal()
            if not self.r.path or self.r.path[-1] != goal:
                self.r.path = self.spatial.astar(self.r.position, goal)
            if len(self.r.path) > 1:
                nxt = self.r.path[1]
                if nxt not in reserved:
                    old = self.r.position
                    self.r.position = nxt
                    self.r.path = self.r.path[1:]
                    self.r.energy = max(0, self.r.energy - 0.035)
                    self.r.hunger = min(100, self.r.hunger + 0.025)
                    self.cog._record_hard_case_success("collision")
                    events.append(
                        {
                            "type": "move",
                            "tick": tick,
                            "agent_id": self.r.agent_id,
                            "from": list(old),
                            "to": list(nxt),
                        }
                    )
                else:
                    # Hard-case mining: streak di collisioni consecutive ->
                    # salienza crescente in memoria locale (retrieval piu'
                    # probabile su questo ostacolo), reset al primo passo libero.
                    streak = self.cog._record_hard_case_failure("collision")
                    salience = min(0.2 + 0.1 * streak, 0.9)
                    self.cog.memory.add(
                        tick, "collision", f"Cella {nxt} occupata (streak={streak})", salience
                    )
                    events.append(
                        {
                            "type": "wait",
                            "tick": tick,
                            "agent_id": self.r.agent_id,
                            "at": list(self.r.position),
                            "reason": "reserved",
                        }
                    )

        if self.r.state == AgentState.WORKING:
            self.r.money += self.economy.wage(self.r) / 60.0
            self.r.energy = max(0, self.r.energy - 0.025)
            self.r.hunger = min(100, self.r.hunger + 0.04)
            if self.r.career_decided_day != day and self.r.position == self._goal():
                self.r.career_decided_day = day
                self._paperclip_checkout(tick, day, "career")
                career = await self.cog.decide_career(tick)
                self._paperclip_complete(
                    tick, day, "career", career.get("thought", career.get("choice", ""))
                )
                events.append(
                    {
                        "type": "career_decision",
                        "tick": tick,
                        "agent_id": self.r.agent_id,
                        "choice": career["choice"],
                        "thought": career["thought"],
                        "confidence": career.get("confidence", 0.0),
                    }
                )
                change = self.economy.apply_job(tick, self.r, career["choice"])
                if change:
                    events.append(change)
            if self.r.position == self._goal():
                await self._maybe_build(tick, day, events)
                await self._maybe_govern(tick, day, events)
                await self._maybe_room(tick, day, events)

        elif self.r.state == AgentState.EATING and self.r.position == self._goal():
            if self.r.money >= 0.03:
                self.r.money -= 0.03
                self.r.hunger = max(0, self.r.hunger - 0.8)
            if self.construction is not None:
                self.construction.record_visit(self.r.target_poi, self.r.agent_id)
            await self._maybe_room(tick, day, events)

        elif self.r.state == AgentState.REST:
            self.r.energy = min(100, self.r.energy + 0.3)
            self.r.hunger = min(100, self.r.hunger + 0.01)
            if self.r.reflected_day != day:
                self.r.reflected_day = day
                self._paperclip_checkout(tick, day, "reflect")
                strategy, applied = await self.cog.reflect(tick)
                self._paperclip_complete(tick, day, "reflect", strategy)
                events.append(
                    {
                        "type": "reflection",
                        "tick": tick,
                        "agent_id": self.r.agent_id,
                        "thought": strategy,
                        "focus": applied.get("focus"),
                        "lesson": applied.get("lesson"),
                    }
                )
                # Dopo reflect: ricerca collettiva → vault (una volta/giorno)
                if self.research is not None and self.r.research_decided_day != day:
                    self.r.research_decided_day = day
                    res = await self.research.research_agent(
                        agent_id=self.r.agent_id,
                        tick=tick,
                        prompt=self.cog.prompt(),
                        money=self.r.money,
                        job=self.r.job,
                        focus=self.cog.improve.focus,
                    )
                    improve_meta = None
                    if res.get("self_improve") and res.get("choice") in (
                        "write_lesson",
                        "write_discovery",
                    ):
                        improve_meta = self.cog.improve.apply_research_insight(
                            tick,
                            topic=str(res.get("topic") or "research"),
                            thought=str(res.get("thought") or ""),
                            from_web=bool(res.get("from_web")),
                        )
                        self.r.last_thought = improve_meta.get("lesson") or self.r.last_thought
                    events.append(
                        {
                            "type": "research_decision",
                            "tick": tick,
                            "agent_id": self.r.agent_id,
                            "choice": res.get("choice"),
                            "thought": res.get("thought"),
                            "topic": res.get("topic"),
                            "query": res.get("query"),
                            "web_hits": res.get("web_hits", 0),
                            "from_web": res.get("from_web", False),
                            "stored": res.get("stored", False),
                            "vault": res.get("vault"),
                            "self_improve": improve_meta,
                        }
                    )
            await self._maybe_room(tick, day, events)

        elif self.r.state == AgentState.EXPLORING and self.r.position == self._goal():
            self.r.energy = max(0, self.r.energy - 0.02)
            self.r.hunger = min(100, self.r.hunger + 0.03)
            self.r.last_thought = f"Esploro fuori città · {self.r.target_poi}"
            events.append(
                {
                    "type": "explore",
                    "tick": tick,
                    "agent_id": self.r.agent_id,
                    "at": list(self.r.position),
                    "landmark": self.r.target_poi,
                }
            )

        elif self.r.state == AgentState.SOCIALIZING and self.r.position == self._goal():
            if self.construction is not None:
                self.construction.record_visit(self.r.target_poi, self.r.agent_id)
            if self.r.social_decided_day != day:
                self.r.social_decided_day = day
                self._paperclip_checkout(tick, day, "social")
                social = await self.cog.decide_social(tick)
                self._paperclip_complete(
                    tick, day, "social", social.get("thought", social.get("choice", ""))
                )
                events.append(
                    {
                        "type": "social_decision",
                        "tick": tick,
                        "agent_id": self.r.agent_id,
                        "choice": social["choice"],
                        "thought": social["thought"],
                    }
                )
            await self._maybe_build(tick, day, events)
            await self._maybe_govern(tick, day, events)
            await self._maybe_room(tick, day, events)

        if self.r.state == AgentState.ATTENDING_CLASS and self.r.position == self._goal():
            if self.r.study_focused_day != day:
                self.r.study_focused_day = day
                self._paperclip_checkout(tick, day, "study")
                study = await self.cog.decide_study(tick)
                self._paperclip_complete(
                    tick, day, "study", study.get("thought", study.get("choice", ""))
                )
                events.append(
                    {
                        "type": "study_decision",
                        "tick": tick,
                        "agent_id": self.r.agent_id,
                        "choice": study["choice"],
                        "thought": study["thought"],
                    }
                )
                course = self.r.course_id()
                self.r.target_poi = COURSES[course][0]
                self.r.path = self.spatial.astar(self.r.position, self._goal())

            course = self.r.course_id()
            self.r.study_progress[course] = self.r.study_progress.get(course, 0) + 1
            if self.cog.improve.focus == "study":
                self.r.study_progress[course] = self.r.study_progress.get(course, 0) + 1
            progress = self.r.study_progress[course]
            if progress >= self.study_required and self.r.exam_attempted_day != day:
                self.r.exam_attempted_day = day
                passed, score, skill = await self.cog.evaluate_exam(tick, course)
                events.append(
                    {
                        "type": "exam_result",
                        "tick": tick,
                        "agent_id": self.r.agent_id,
                        "course": course,
                        "passed": passed,
                        "score": score,
                        "skill": skill,
                        "thought": self.r.last_thought,
                    }
                )
                if passed:
                    change = self.economy.hire_if_eligible(tick, self.r)
                    if change:
                        events.append(change)

        events.append({"type": "snapshot", "tick": tick, **self.r.snapshot()})
        return events
