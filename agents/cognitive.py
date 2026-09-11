"""Motore cognitivo per agente: memoria privata + Alveare condiviso + self-improve."""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import Dict, List, Optional

from agents.agi_os import AgiOsKernel
from agents.escalation import EscalationGate
from agents.fep import PostureExperience
from agents.memory import EpisodicMemory
from agents.models import AgentRuntime
from agents.self_improve import SelfImprovementLoop
from agents.vault_skills import inject_skill
from config import COURSES
from knowledge.batch import AlveareBatchBuffer
from knowledge.client import AlveareClient
from llm.router import CognitiveRouter
from security.pii import PIISanitizer

REFLECTION_POSTURES = ["consolidate_skills", "recover_energy", "seek_social", "push_study"]

# Hard-case mining (vedi vault/06-MEMORY/wiki/self-learning-loop.md): un
# fallimento ripetuto sullo stesso topic alza deterministicamente salienza
# locale e priorita' di retrieval condiviso, invece di restare una lesson
# piatta identica a tutte le altre. Cap + decay giornaliero evitano che un
# topic monopolizzi la cognizione dell'agente (rischio segnalato in modo
# convergente dal consiglio multi-modello esterno 2026-09-10).
HARD_CASE_STREAK_CAP = 6


def _normalize_chunks(hits: list) -> list:
    """Solo campi stabili per trace/replay (testo completo, non solo id)."""
    out = []
    for h in hits or []:
        out.append(
            {
                "id": str(h.get("id") or ""),
                "source": str(h.get("source") or ""),
                "text": str(h.get("text") or ""),
                "score": float(h.get("score") or 0.0),
                "agent_id": h.get("agent_id"),
                "tick": h.get("tick"),
                "tags": list(h.get("tags") or []),
            }
        )
    out.sort(key=lambda x: (-x["score"], x["id"]))
    return out


class AgentCognitiveEngine:
    def __init__(
        self,
        runtime: AgentRuntime,
        router: CognitiveRouter,
        seed: int,
        embed_dim: int,
        *,
        alveare: AlveareClient | None = None,
        alveare_batch: AlveareBatchBuffer | None = None,
    ):
        self.r = runtime
        self.router = router
        self.seed = seed
        self.memory = EpisodicMemory(embed_dim)
        self.strategy = "Rispetta gli impegni, preserva energia e apprendi competenze utili."
        self.alveare = alveare
        self.alveare_batch = alveare_batch
        self.hard_case_streak: Dict[str, int] = {}
        self.posture_experience = PostureExperience(REFLECTION_POSTURES)
        self._last_posture: Optional[str] = None
        self.escalation_gate = EscalationGate()
        if not self.r.active_course:
            self.r.active_course = self.r.persona.preferred_course
        self.improve = SelfImprovementLoop(
            runtime, router, alveare_batch=alveare_batch
        )
        self.agi_os = AgiOsKernel(
            runtime,
            improve=self.improve,
            strategy=self.strategy,
        )

    def prompt(self) -> str:
        p = self.r.persona
        base = (
            f"Sei {p.display_name}, {p.age} anni. {p.biography} "
            f"Skill={self.r.skills}; lavoro={self.r.job}; corso={self.r.course_id()}; "
            f"focus={self.improve.focus}; strategia={self.strategy}. "
            "Scegli solo tra le opzioni date e restituisci JSON: "
            '{"choice":"...","thought":"...","confidence":0.0}.'
        )
        self.agi_os.set_strategy(self.strategy)
        self.agi_os.bind_improve(self.improve)
        return self.agi_os.boot_prompt(base)

    def _record_hard_case_failure(self, topic: str) -> int:
        n = min(self.hard_case_streak.get(topic, 0) + 1, HARD_CASE_STREAK_CAP)
        self.hard_case_streak[topic] = n
        return n

    def _record_hard_case_success(self, topic: str) -> None:
        self.hard_case_streak.pop(topic, None)

    def _hard_case_tags(self, topic: str, skill: Optional[str] = None) -> List[str]:
        n = self.hard_case_streak.get(topic, 0)
        if n <= 0:
            return []
        tags = ["hard_case", f"obstacle:{topic}", f"severity:{n}"]
        if skill:
            tags.append(f"skill_gap:{skill}")
        return tags

    def _hard_case_query_suffix(self) -> str:
        """Funzione pura dello stato locale: stessi streak -> stessa query -> stesso rid."""
        active = sorted(k for k, v in self.hard_case_streak.items() if v > 0)
        return (" hard_case " + " ".join(active)) if active else ""

    def _decay_hard_case_streaks(self) -> None:
        """Decadimento deterministico giornaliero (mitiga la fossilizzazione su un topic)."""
        for k in list(self.hard_case_streak.keys()):
            n = self.hard_case_streak[k] - 1
            if n <= 0:
                del self.hard_case_streak[k]
            else:
                self.hard_case_streak[k] = n

    def _retrieve_alveare(
        self, tick: int, event: str, query: str, *, tags: Optional[List[str]] = None
    ) -> list:
        """Retrieval tracciato: replay usa chunk completi dal trace, non lo store live.

        `tags` (consiglio esterno, 2026-09-11, "Metadata filtering"):
        senza filtro, un agente che studia webgl puo' recuperare chunk su
        motion e viceversa, degradando la coerenza della riflessione LLM. I
        tag entrano nel payload -> il rid cambia se cambiano, quindi la
        cache/replay restano corrette (stesso principio del resto del router)."""
        payload = {
            "kind": "alveare_retrieval",
            "agent_id": self.r.agent_id,
            "tick": tick,
            "event": event,
            "query": query,
            "tags": sorted(tags) if tags else None,
        }
        rid = self.router._id(payload)
        recorded = self.router.trace.get(rid)
        if isinstance(recorded, dict) and "chunks" in recorded:
            return list(recorded["chunks"])
        hits: list = []
        if self.alveare is not None:
            hits = self.alveare.query(query, k=4, tags=tags)
        chunks = _normalize_chunks(hits)
        self.router.trace.put(rid, payload, {"chunks": chunks})
        return chunks

    def _enqueue_shared(self, tick: int, text: str, tags: Optional[List[str]] = None) -> None:
        clean = PIISanitizer.sanitize_text(text)
        if self.alveare_batch is not None:
            self.alveare_batch.enqueue(
                agent_id=self.r.agent_id,
                tick=tick,
                text=clean,
                source="agent",
                tags=tags or ["reflection"],
            )

    async def decision(self, tick: int, event: str, choices: List[str], context: dict):
        recalled = [asdict(m) for m in self.memory.search(event, 4)]
        shared = self._retrieve_alveare(tick, event, event)
        d = await self.router.decide(
            agent_id=self.r.agent_id,
            tick=tick,
            event=event,
            choices=choices,
            system_prompt=inject_skill(self.prompt(), event),
            context={**context, "memories": recalled, "alveare": shared},
        )
        self.r.last_thought = d.thought
        self.memory.add(tick, "decision", f"{event}: {d.choice}. {d.thought}", 0.65)
        self._enqueue_shared(tick, f"{event}: {d.choice}. {d.thought}", ["decision"])
        return d

    async def evaluate_exam(self, tick: int, course_id: str):
        _, skill, difficulty = COURSES[course_id]
        p = self.r.persona
        progress = self.r.study_progress.get(course_id, 0)
        raw = hashlib.sha256(
            f"{self.seed}:{self.r.agent_id}:{course_id}:{tick // 600}".encode()
        ).hexdigest()
        noise = int(raw[:6], 16) % 31 - 15
        score = round(30 * p.diligence + 25 * p.curiosity + min(progress, 30) + noise)
        passed = score >= difficulty
        topic = f"study:{course_id}"
        if passed and skill not in self.r.skills:
            self.r.skills.append(skill)
            self._record_hard_case_success(topic)
            thought = f"Ho superato {course_id}: ora possiedo la skill {skill}."
            self.memory.add(tick, "skill_unlock", thought, 1.0)
            self._enqueue_shared(tick, thought, ["skill_unlock", "self_improve"])
        else:
            streak = self._record_hard_case_failure(topic)
            thought = (
                f"Risultato {score}; devo migliorare la preparazione per {course_id} "
                f"(tentativo a rischio #{streak}, skill_gap {skill})."
            )
            # BUGFIX: prima kind="exam" — reflect() conta i fallimenti su
            # kind=="exam_failed", quindi gli esami bocciati non venivano mai
            # contati. Salienza cresce con lo streak (hard-case mining).
            salience = min(0.85 + 0.05 * streak, 1.0)
            self.memory.add(tick, "exam_failed", thought, salience)
            self._enqueue_shared(
                tick, thought, ["exam", "self_improve"] + self._hard_case_tags(topic, skill)
            )
        self.r.last_thought = thought
        return passed, score, skill

    def _fep_posture_scores(self) -> Dict[str, float]:
        """Punteggio deterministico ispirato ad Active Inference / Free Energy
        Principle (Friston): value(postura) = instrumental (soddisfa un bisogno
        fisiologico/sociale noto) + epistemic (riduce un'incertezza nota, es. uno
        skill-gap attivo da hard-case mining). Non e' vera inferenza bayesiana —
        sono rapporti su contatori/stato locale dell'agente, funzione pura, mai
        LLM/RNG. Rimpiazza la scelta arbitraria (hash) del fallback del router
        quando l'LLM e' disabilitato (default), senza toccare il path LLM/replay.
        Verificato con un consiglio esterno multi-modello (2026-09-10):
        pymdp (infer-actively) e' la libreria di riferimento per
        Active Inference in Python, ma calibrarla per 50 agenti e mantenerla
        bit-per-bit deterministica e' un costo non giustificato rispetto a
        un'euristica dedicata — vedi vault/05-SESSIONS per la sintesi completa."""
        r = self.r
        energy_gap = max(0.0, 100.0 - r.energy) / 100.0
        hunger_gap = min(1.0, r.hunger / 100.0)
        social_gap = max(0.0, 1.0 - min(1.0, len(r.relationships) / 5.0))
        active_gaps = sum(1 for v in self.hard_case_streak.values() if v > 0)
        epistemic_study = min(1.0, 0.34 * active_gaps)
        baseline = max(0.0, 1.0 - (energy_gap + social_gap + epistemic_study) / 3.0)
        return {
            "recover_energy": 0.7 * energy_gap + 0.3 * hunger_gap,
            "seek_social": social_gap,
            "push_study": epistemic_study,
            "consolidate_skills": baseline,
        }

    def _escalation_signal(self) -> float:
        """[0,1]: quanto e' critica la situazione dell'agente oggi, riusando lo
        stesso streak gia' verificato dall'hard-case mining. Segnale deterministico
        e puro, input al gate a isteresi (agents/escalation.py) che decide se
        tentare Tier 1 (LLM vera) invece del Tier 0 (euristica) di default."""
        max_streak = max(self.hard_case_streak.values(), default=0)
        return min(1.0, max_streak / HARD_CASE_STREAK_CAP)

    async def reflect(self, tick: int):
        recent = self.memory.recent(12)
        successes = sum(x.kind == "skill_unlock" for x in recent)
        failures = sum(x.kind in ("collision", "exam_failed") for x in recent)
        scores = self._fep_posture_scores()
        if self._last_posture is not None:
            # Outcome della postura scelta ieri: se il bisogno che doveva coprire
            # e' oggi basso, ha funzionato (reward alto). Expected Free Energy
            # (Active Inference) applicata alla scelta di postura — qui
            # l'"osservazione" e' il gap residuo stesso, non serve uno
            # snapshot pre/post separato.
            residual_gap = scores.get(self._last_posture, 0.5)
            self.posture_experience.record_outcome(self._last_posture, 1.0 - 2.0 * residual_gap)
        template = (
            f"Per il prossimo giorno: consolida {successes} successi, "
            f"riduci {failures} ostacoli, privilegia studio e relazioni positive."
        )
        postures = REFLECTION_POSTURES
        query = f"reflection day successes={successes} failures={failures}"
        query += self._hard_case_query_suffix()
        shared = self._retrieve_alveare(tick, "daily_reflection", query)
        reflect_prompt = (
            f"{self.prompt()} Hai appena concluso la giornata: {successes} successi, "
            f"{failures} ostacoli. Rifletti brevemente e scegli la postura strategica "
            "per domani tra le opzioni date."
        )
        escalate = self.escalation_gate.decide(self._escalation_signal())
        d = await self.router.decide(
            agent_id=self.r.agent_id,
            tick=tick,
            event="daily_reflection",
            choices=postures,
            system_prompt=inject_skill(reflect_prompt, "daily_reflection"),
            context={
                "successes": successes,
                "failures": failures,
                "recent_memories": [asdict(m) for m in recent],
                "alveare": shared,
            },
            escalate=escalate,
        )
        self.escalation_gate.note_cycle_result(escalated=escalate)
        # d.source e' fissato alla PRIMA scrittura nel trace (llm/router.py) e persiste
        # identico su ogni replay successivo: a differenza dei vecchi contatori globali
        # router.stats["live"]/["replay"] (confusi da chiamate concorrenti di altri
        # agenti e da cache condivisa fra run separate), non dipende da stato mutabile
        # esterno a questa singola decisione -> stesso rid, stesso source, sempre.
        used_live_or_replay = d.source == "live"
        self.strategy = d.thought if (used_live_or_replay and d.thought) else template
        self.r.last_thought = self.strategy
        self.memory.add(tick, "reflection", self.strategy, 0.95)
        self._enqueue_shared(tick, self.strategy, ["reflection"])
        posture_choice = d.choice
        if not used_live_or_replay:
            # Bisogno immediato (scores) combinato con l'esperienza appresa nei
            # giorni precedenti (Expected Free Energy, bassa = meglio -> sottrai).
            now_scores = self._fep_posture_scores()
            posture_choice = max(
                postures,
                key=lambda p: (
                    now_scores.get(p, 0.0) - self.posture_experience.expected_free_energy(p),
                    p,
                ),
            )
        self._last_posture = posture_choice
        applied = self.improve.apply_posture(tick, posture_choice, self.strategy)
        self._decay_hard_case_streaks()
        return self.strategy, applied

    async def decide_career(self, tick: int) -> dict:
        shared = self._retrieve_alveare(tick, "career_choice", "career job skills")
        result = await self.improve.career_decision(tick, self.prompt(), shared)
        self.r.last_thought = result["thought"]
        self.memory.add(tick, "career", f"{result['choice']}: {result['thought']}", 0.8)
        return result

    async def decide_study(self, tick: int) -> dict:
        course_id = self.r.course_id()
        skill = COURSES[course_id][1] if course_id in COURSES else None
        shared = self._retrieve_alveare(
            tick, "study_focus", "study course skills", tags=[skill] if skill else None
        )
        result = await self.improve.study_decision(tick, self.prompt(), shared)
        self.r.last_thought = result["thought"]
        self.memory.add(tick, "study", f"{result['choice']}: {result['thought']}", 0.75)
        return result

    async def decide_social(self, tick: int) -> dict:
        shared = self._retrieve_alveare(tick, "social_stance", "social plaza")
        result = await self.improve.social_decision(tick, self.prompt(), shared)
        self.r.last_thought = result["thought"]
        self.memory.add(tick, "social", f"{result['choice']}: {result['thought']}", 0.55)
        return result

    async def decide_build(
        self,
        tick: int,
        *,
        open_kinds: list,
        can_propose: list,
        can_relocate: list | None = None,
        can_join_crew_ids: list | None = None,
    ) -> dict:
        shared = self._retrieve_alveare(tick, "build_choice", "build cafe city escrow")
        result = await self.improve.build_decision(
            tick,
            self.prompt(),
            shared,
            open_kinds=open_kinds,
            can_propose=can_propose,
            can_relocate=can_relocate or [],
            can_join_crew_ids=can_join_crew_ids or [],
        )
        self.r.last_thought = result["thought"]
        self.memory.add(tick, "build", f"{result['choice']}: {result['thought']}", 0.85)
        return result

    async def decide_room(self, tick: int, *, poi: str, choices: list, room_summary: dict) -> dict:
        shared = self._retrieve_alveare(tick, "room_choice", f"decorate room {poi} furniture theme")
        result = await self.improve.room_decision(
            tick,
            self.prompt(),
            shared,
            poi=poi,
            choices=choices,
            room_summary=room_summary,
        )
        self.r.last_thought = result["thought"]
        self.memory.add(tick, "room", f"{poi}:{result['choice']}: {result['thought']}", 0.8)
        return result

    async def decide_governance(
        self,
        tick: int,
        *,
        can_propose_kinds: list,
        has_unvoted: bool,
        open_kinds: list,
    ) -> dict:
        shared = self._retrieve_alveare(tick, "governance_choice", "governance vote proposal city rule")
        result = await self.improve.governance_decision(
            tick,
            self.prompt(),
            shared,
            can_propose_kinds=can_propose_kinds,
            has_unvoted=has_unvoted,
            open_kinds=open_kinds,
        )
        self.r.last_thought = result["thought"]
        self.memory.add(tick, "governance", f"{result['choice']}: {result['thought']}", 0.85)
        return result
