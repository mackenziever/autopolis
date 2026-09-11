"""Apparato di auto-miglioramento agente (FreeLLM + Alveare).

Fuori dal hot-path movimento: chiamato solo su eventi rari (reflect, career,
study focus, social). Scrive lesson nell'Alveare e aggiorna focus/corso/lavoro.
"""
from __future__ import annotations

from typing import List

from agents.models import AgentRuntime
from agents.vault_skills import inject_skill
from config import COURSES, JOBS
from knowledge.batch import AlveareBatchBuffer
from llm.router import CognitiveRouter
from security.pii import PIISanitizer


POSTURE_TO_FOCUS = {
    "consolidate_skills": "study",
    "push_study": "study",
    "recover_energy": "rest",
    "seek_social": "social",
    "apply_promotion": "career",
    "keep_job": "career",
    "switch_course": "study",
    "stay_course": "study",
}


class SelfImprovementLoop:
    def __init__(
        self,
        runtime: AgentRuntime,
        router: CognitiveRouter,
        *,
        alveare_batch: AlveareBatchBuffer | None = None,
    ):
        self.r = runtime
        self.router = router
        self.alveare_batch = alveare_batch
        self.focus = "study"
        self.lessons: List[str] = []
        self.stats = {"improves": 0, "career": 0, "study": 0, "social": 0}

    def _publish(self, tick: int, text: str, tags: List[str]) -> None:
        if not self.alveare_batch:
            return
        self.alveare_batch.enqueue(
            agent_id=self.r.agent_id,
            tick=tick,
            text=PIISanitizer.sanitize_text(text),
            source="agent",
            tags=tags,
        )

    def apply_posture(self, tick: int, choice: str, thought: str) -> dict:
        self.focus = POSTURE_TO_FOCUS.get(choice, self.focus)
        lesson = f"[{self.r.agent_id}] posture={choice} focus={self.focus} | {thought}"
        self.lessons.append(lesson)
        if len(self.lessons) > 32:
            self.lessons = self.lessons[-32:]
        self._publish(tick, lesson, ["self_improve", "posture", self.focus])
        self.stats["improves"] += 1
        # Micro-boost deterministico sul focus scelto (non LLM): accelera studio
        if self.focus == "study":
            course = self.r.active_course or self.r.persona.preferred_course
            self.r.study_progress[course] = self.r.study_progress.get(course, 0) + 2
            self.stats["study"] += 1
        return {"focus": self.focus, "lesson": lesson}

    def apply_research_insight(
        self,
        tick: int,
        *,
        topic: str,
        thought: str,
        from_web: bool = False,
    ) -> dict:
        """Dopo research→vault: boost studio + memoria Alveare (automiglioramento)."""
        course = self.r.active_course or self.r.persona.preferred_course
        boost = 4 if from_web else 2
        self.r.study_progress[course] = self.r.study_progress.get(course, 0) + boost
        if from_web and self.focus != "study":
            # Insight dal web tende a ripuntare sul focus studio/costruzione
            self.focus = "study" if "city" not in (topic or "") else "career"
        lesson = (
            f"[{self.r.agent_id}] research/{topic} web={int(from_web)} "
            f"boost={boost} course={course} | {thought}"
        )
        self.lessons.append(lesson)
        if len(self.lessons) > 32:
            self.lessons = self.lessons[-32:]
        tags = ["self_improve", "research", topic or "general"]
        if from_web:
            tags.append("web")
        self._publish(tick, lesson, tags)
        self.stats["improves"] += 1
        self.stats["study"] += 1
        return {
            "focus": self.focus,
            "lesson": lesson,
            "boost": boost,
            "course": course,
            "from_web": from_web,
        }

    def eligible_jobs(self) -> List[str]:
        roles = [
            role
            for role, (skill, _wage, _slots) in JOBS.items()
            if skill in self.r.skills or skill == "basic_literacy"
        ]
        if self.r.job not in roles:
            roles.append(self.r.job)
        return sorted(set(roles))[:6] or ["intern"]

    async def career_decision(self, tick: int, prompt: str, shared: list) -> dict:
        choices = self.eligible_jobs()
        if len(choices) < 2:
            choices = list(choices) + ["train_more"]
        d = await self.router.decide(
            agent_id=self.r.agent_id,
            tick=tick,
            event="career_choice",
            choices=choices,
            system_prompt=inject_skill(prompt, "career_choice"),
            context={
                "job": self.r.job,
                "skills": list(self.r.skills),
                "money": self.r.money,
                "alveare": shared,
                "focus": self.focus,
            },
        )
        self.stats["career"] += 1
        self._publish(
            tick,
            f"[{self.r.agent_id}] career→{d.choice}: {d.thought}",
            ["self_improve", "career"],
        )
        return {"choice": d.choice, "thought": d.thought, "confidence": d.confidence}

    async def study_decision(self, tick: int, prompt: str, shared: list) -> dict:
        courses = sorted(COURSES.keys())
        d = await self.router.decide(
            agent_id=self.r.agent_id,
            tick=tick,
            event="study_focus",
            choices=courses,
            system_prompt=inject_skill(prompt, "study_focus"),
            context={
                "preferred": self.r.persona.preferred_course,
                "active": self.r.active_course,
                "progress": dict(self.r.study_progress),
                "skills": list(self.r.skills),
                "alveare": shared,
                "focus": self.focus,
            },
        )
        if d.choice in COURSES:
            self.r.active_course = d.choice
        self.stats["study"] += 1
        self._publish(
            tick,
            f"[{self.r.agent_id}] study→{d.choice}: {d.thought}",
            ["self_improve", "study"],
        )
        return {"choice": d.choice, "thought": d.thought, "confidence": d.confidence}

    async def social_decision(self, tick: int, prompt: str, shared: list) -> dict:
        choices = ["approach", "observe", "rest_social"]
        d = await self.router.decide(
            agent_id=self.r.agent_id,
            tick=tick,
            event="social_stance",
            choices=choices,
            system_prompt=inject_skill(prompt, "social_stance"),
            context={
                "sociability": self.r.persona.sociability,
                "energy": self.r.energy,
                "alveare": shared,
                "focus": self.focus,
            },
        )
        self.stats["social"] += 1
        self._publish(
            tick,
            f"[{self.r.agent_id}] social→{d.choice}: {d.thought}",
            ["self_improve", "social"],
        )
        return {"choice": d.choice, "thought": d.thought, "confidence": d.confidence}

    async def build_decision(
        self,
        tick: int,
        prompt: str,
        shared: list,
        *,
        open_kinds: List[str],
        can_propose: List[str],
        can_relocate: List[str] | None = None,
        can_join_crew_ids: List[str] | None = None,
    ) -> dict:
        """Scelta costruzione: proporre (escrow) / contribuire / rilocare / skip.

        BUGFIX: prima `join_crew` era una scelta generica unica — con piu'
        rilocazioni aperte in parallelo, ogni join finiva sempre sul primo
        progetto (`construction.join_crew()` senza `project_id` prende
        `open_relocations()[0]`), affamando tutte le altre. Ora una scelta
        `join_crew_<project_id>` per ciascun progetto realmente unito-abile,
        stesso pattern gia' usato per `propose_relocate_<poi>`."""
        choices = ["skip_build", "contribute"]
        for k in can_propose:
            choices.append(f"propose_{k}")
        for poi in can_relocate or []:
            choices.append(f"propose_relocate_{poi}")
        for project_id in can_join_crew_ids or []:
            choices.append(f"join_crew_{project_id}")
        # Deduplicate preserve order
        seen = set()
        uniq = []
        for c in choices:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        d = await self.router.decide(
            agent_id=self.r.agent_id,
            tick=tick,
            event="build_choice",
            choices=uniq,
            system_prompt=inject_skill(prompt, "build_city"),
            context={
                "money": self.r.money,
                "job": self.r.job,
                "open_projects": open_kinds,
                "can_propose": can_propose,
                "can_relocate": can_relocate or [],
                "can_join_crew_ids": can_join_crew_ids or [],
                "alveare": shared,
                "focus": self.focus,
            },
        )
        self.stats["social"] += 1  # civic action
        self._publish(
            tick,
            f"[{self.r.agent_id}] build→{d.choice}: {d.thought}",
            ["self_improve", "build", "city"],
        )
        return {"choice": d.choice, "thought": d.thought, "confidence": d.confidence}

    async def room_decision(
        self,
        tick: int,
        prompt: str,
        shared: list,
        *,
        poi: str,
        choices: List[str],
        room_summary: dict,
    ) -> dict:
        """Arreda/gestisci ambiente POI (tema + props) — stile Massive Manas / Sims."""
        uniq = []
        seen: set = set()
        for c in choices or ["skip_room"]:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        d = await self.router.decide(
            agent_id=self.r.agent_id,
            tick=tick,
            event="room_choice",
            choices=uniq,
            system_prompt=inject_skill(prompt, "room_choice"),
            context={
                "money": self.r.money,
                "job": self.r.job,
                "poi": poi,
                "room": room_summary,
                "alveare": shared,
                "focus": self.focus,
            },
        )
        self.stats["social"] += 1
        self._publish(
            tick,
            f"[{self.r.agent_id}] room@{poi}→{d.choice}: {d.thought}",
            ["self_improve", "room", "city"],
        )
        return {"choice": d.choice, "thought": d.thought, "confidence": d.confidence}

    async def governance_decision(
        self,
        tick: int,
        prompt: str,
        shared: list,
        *,
        can_propose_kinds: List[str],
        has_unvoted: bool,
        open_kinds: List[str],
    ) -> dict:
        """Scelta civica: proporre un'ordinanza / votare quella aperta / skip.

        La scelta qui e' solo QUALE azione tentare — il tally del voto resta
        una funzione deterministica in world/governance.py, mai l'LLM.
        """
        choices = ["skip_governance"]
        if has_unvoted:
            choices += ["vote_yes", "vote_no", "vote_abstain"]
        for k in can_propose_kinds:
            choices.append(f"propose_{k}")
        seen: set = set()
        uniq = []
        for c in choices:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        d = await self.router.decide(
            agent_id=self.r.agent_id,
            tick=tick,
            event="governance_choice",
            choices=uniq,
            system_prompt=inject_skill(prompt, "governance_city"),
            context={
                "money": self.r.money,
                "open_proposals": open_kinds,
                "can_propose": can_propose_kinds,
                "has_unvoted": has_unvoted,
                "alveare": shared,
                "focus": self.focus,
            },
        )
        self.stats["social"] += 1  # civic action
        self._publish(
            tick,
            f"[{self.r.agent_id}] governance→{d.choice}: {d.thought}",
            ["self_improve", "governance", "city"],
        )
        return {"choice": d.choice, "thought": d.thought, "confidence": d.confidence}
