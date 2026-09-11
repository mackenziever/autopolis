"""Research / learn loop — cerca in Alveare, sintetizza, salva nel vault.

Fuori hot-path movimento. Una volta al giorno per agente (o curator collettivo).
"""
from __future__ import annotations

import hashlib
from typing import Any, List, Optional

from agents.vault_skills import inject_skill
from config import JOBS
from knowledge.vault_librarian import VaultLibrarian
from llm.router import CognitiveRouter
from security.pii import PIISanitizer


RESEARCH_TOPICS = [
    "web design layout information architecture grid awwwards site of the day",
    "career skills portfolio award winning site development",
    "social creative studio collaboration crew feedback critique",
    "self improvement deliberate practice craft mastery design",
    "webgl three.js shader motion gsap animation interaction",
    "typography color palette visual identity web design",
    "agent memory knowledge management design system notes",
]


class ResearchLoop:
    def __init__(
        self,
        router: CognitiveRouter,
        librarian: VaultLibrarian,
        *,
        alveare=None,
        web_search=None,
    ):
        self.router = router
        self.librarian = librarian
        self.alveare = alveare
        self.web_search = web_search
        self.stats = {"researches": 0, "writes": 0, "web_searches": 0, "fallback_skipped": 0}

    def stats_summary(self) -> dict:
        """Tassi derivati per /health (approfondimento RSI, 2026-09-11): un
        write_rate basso o un fallback_rate alto sono il segnale precoce del
        bug corretto oggi (budget esaurito -> fallback -> placeholder scritto
        nel vault come se fosse conoscenza reale) — visibile qui prima che
        serva rileggere a mano centinaia di file di discovery per notarlo."""
        s = self.stats
        researches = s["researches"]
        return {
            "write_rate": round(s["writes"] / researches, 4) if researches else 0.0,
            "fallback_rate": round(s["fallback_skipped"] / researches, 4) if researches else 0.0,
        }

    def _retrieve(self, query: str, k: int = 5, *, tags: Optional[List[str]] = None) -> List[dict]:
        if not self.alveare:
            return []
        try:
            return list(self.alveare.query(query, k=k, tags=tags) or [])
        except Exception:
            return []

    async def _search_web(
        self, query: str, *, agent_id: str = "", tick: int = 0, event: str = "research_focus"
    ) -> List[dict]:
        """Ricerca internet reale (opzionale). Fuori hot-path, cache per replay.

        Consiglio esterno (2026-09-11, "1. Cache deterministica"): la
        cache di WebSearchClient era chiavata solo sul testo della query — due
        (agent_id, tick) diversi con lo stesso testo (plausibile: topic_base +
        focus + job ricadono spesso sulle stesse combinazioni) condividevano
        silenziosamente lo stesso risultato. Passare il contesto rende ogni
        combinazione (agent_id, tick, event) una chiave di cache distinta,
        come gia' fa llm/router.py per le chiamate LLM."""
        if not self.web_search:
            return []
        try:
            hits = await self.web_search.search(
                query, agent_id=agent_id, tick=tick, event=event
            )
        except Exception:
            return []
        self.stats["web_searches"] += 1
        return [
            {
                "text": f"{h.get('title', '')} — {h.get('snippet', '')}".strip(" —"),
                "source": h.get("url", ""),
            }
            for h in hits
            if h.get("title") or h.get("snippet")
        ]

    async def research_agent(
        self,
        *,
        agent_id: str,
        tick: int,
        prompt: str,
        money: float = 0.0,
        job: str = "",
        focus: str = "",
    ) -> dict:
        """L'agente cerca conoscenza condivisa e scrive una discovery/lesson.

        BUGFIX determinismo: hash() nativo di Python e' randomizzato per
        processo (PYTHONHASHSEED); su due run identiche produceva topic
        diversi fin dal tick 0. sha256 e' stabile fra processi, come nel
        resto del codebase (world/social.py, world/construction.py._pid).
        """
        raw = hashlib.sha256(f"{agent_id}:{tick // 600}".encode()).hexdigest()
        topic_idx = int(raw[:8], 16) % len(RESEARCH_TOPICS)
        topic_base = RESEARCH_TOPICS[topic_idx]
        # Personalizza la query web con focus/lavoro (deterministico, no RNG).
        topic_q = " ".join(
            p for p in (topic_base, focus or "", job or "", "autonomous agent learning") if p
        ).strip()
        skill = JOBS[job][0] if job in JOBS and job != "intern" else None
        hits = self._retrieve(topic_base, k=5, tags=[skill] if skill else None)
        snippets = [
            PIISanitizer.sanitize_text(str(h.get("text") or ""))[:240]
            for h in hits
            if h.get("text")
        ]
        web_hits = await self._search_web(
            topic_q, agent_id=agent_id, tick=tick, event="research_focus"
        )
        web_snippets = [
            PIISanitizer.sanitize_text(str(h.get("text") or ""))[:240] for h in web_hits
        ]
        choices = ["write_lesson", "write_discovery", "skip_research"]
        ctx = {
            "topic": topic_q,
            "alveare_hits": snippets,
            "web_hits": web_snippets,
            "money": money,
            "job": job,
            "focus": focus,
        }
        web_note = (
            "Hai anche accesso a risultati di ricerca internet reali su questo tema. "
            "Usa il web per automigliorarti e immagazzinare conoscenza utile alla città. "
            if web_hits
            else "Se il web non risponde, sintetizza dalle memorie Alveare. "
        )
        system = (
            f"{prompt} Stai esplorando conoscenza (Alveare + web) sul tema '{topic_base}'. {web_note}"
            "Se trovi insight utili, scegli write_lesson (lezione operativa per te e gli altri) o "
            "write_discovery (scheda wiki condivisa); altrimenti skip_research. "
            "JSON solo choice/thought/confidence."
        )
        d = await self.router.decide(
            agent_id=agent_id,
            tick=tick,
            event="research_focus",
            choices=choices,
            system_prompt=inject_skill(system, "research_focus"),
            context=ctx,
        )
        self.stats["researches"] += 1
        out: dict[str, Any] = {
            "choice": d.choice,
            "thought": d.thought,
            "confidence": d.confidence,
            "topic": topic_base,
            "query": topic_q,
            "hits": len(snippets),
            "web_hits": len(web_snippets),
            "from_web": bool(web_hits),
            "stored": False,
            "self_improve": False,
        }
        if d.choice == "skip_research":
            return out
        if d.source != "live":
            # Bugfix (2026-09-11, "gli agenti non si automigliorano"): il router
            # in fallback sceglie comunque deterministicamente fra write_lesson/
            # write_discovery/skip_research (hash sul rid, non sul contenuto) —
            # senza questo controllo, il placeholder "Fallback deterministico per
            # research_focus (...)" veniva scritto nel vault/Alveare come se fosse
            # una vera scoperta, e poi RIPESCATO da altri agenti come RAG hit
            # (agents/research.py._retrieve, filtrato per tag) — auto-contaminando
            # la base di conoscenza condivisa con rumore invece di sapere reale.
            # Stesso principio gia' applicato a agents/cognitive.py.reflect()
            # (source != "live" -> usa un fallback pulito, mai il placeholder).
            self.stats["fallback_skipped"] += 1
            out["choice"] = "skip_research"
            return out
        thought = PIISanitizer.sanitize_text(d.thought or "")
        topic_slug = topic_base.split()[0]
        if d.choice == "write_lesson":
            wr = self.librarian.record_lesson(
                agent_id=agent_id,
                event="research_focus",
                choice=d.choice,
                lesson=thought,
                tick=tick,
                topic=topic_slug,
                rid=d.rid,
            )
            out["vault"] = wr
            out["stored"] = bool(wr.get("ok"))
            out["self_improve"] = True
            self.stats["writes"] += 1
        elif d.choice == "write_discovery":
            title = f"Research {topic_slug} — {agent_id}"
            body = thought
            if snippets:
                body += "\n\n### Fonti Alveare\n" + "\n".join(f"- {s}" for s in snippets[:4])
            if web_hits:
                body += "\n\n### Fonti Web\n" + "\n".join(
                    f"- {PIISanitizer.sanitize_text(str(h.get('text') or ''))[:240]} ({h.get('source', '')})"
                    for h in web_hits[:4]
                )
            wr = self.librarian.record_discovery(
                title=title,
                body=body,
                tags=["research", "web" if web_hits else "alveare", topic_slug],
                agent_id=agent_id,
                tick=tick,
                rid=d.rid,
            )
            out["vault"] = wr
            out["stored"] = bool(wr.get("ok"))
            out["self_improve"] = True
            self.stats["writes"] += 1
        return out

    def curate_event(self, event: dict) -> Optional[dict]:
        """Salva eventi cognitivi/build nel vault senza LLM (deterministico)."""
        t = event.get("type")
        tick = event.get("tick")
        if t in ("reflection", "career_decision", "study_decision", "social_decision", "build_decision", "room_decision"):
            return self.librarian.record_lesson(
                agent_id=str(event.get("agent_id") or "unknown"),
                event=str(t),
                choice=str(event.get("choice") or event.get("focus") or ""),
                lesson=str(event.get("thought") or event.get("lesson") or ""),
                tick=tick,
                topic=str(t).replace("_decision", "").replace("_", "-"),
            )
        if t == "city_build":
            return self.librarian.record_world_build(
                poi=str(event.get("poi") or "Unknown"),
                meta=event,
                tick=tick,
            )
        if t in ("build_propose", "build_contribute"):
            return self.librarian.record_lesson(
                agent_id=str(event.get("agent_id") or "unknown"),
                event=str(t),
                choice=str(event.get("poi") or event.get("kind") or ""),
                lesson=str(event.get("thought") or ""),
                tick=tick,
                topic="construction",
            )
        if t == "exam_result" and event.get("passed"):
            return self.librarian.record_lesson(
                agent_id=str(event.get("agent_id") or "unknown"),
                event="exam_result",
                choice=str(event.get("skill") or event.get("course") or ""),
                lesson=str(event.get("thought") or f"Passed {event.get('course')}"),
                tick=tick,
                topic="exam",
            )
        if t == "mayor_ruling":
            verdetto = "ratificata" if event.get("final") else "respinta"
            return self.librarian.record_lesson(
                agent_id="mayor",
                event="mayor_ruling",
                choice=str(event.get("choice") or ""),
                lesson=str(event.get("thought") or f"Proposta {event.get('kind')}: {verdetto}."),
                tick=tick,
                topic="governance",
            )
        return None
