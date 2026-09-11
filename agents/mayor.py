"""Sindaco di Civitas: ratifica/veta le proposte del voto popolare.

Ruolo di governance separato dal ciclo cittadino ordinario (agents/state_machine.py
._maybe_govern, world/governance.py) — non un agente FSM, nessun movimento, nessuna
presenza fisica in città. Si attiva SOLO quando una proposta si chiude
(world/governance.py.GovernanceBoard.tick_day), lo stesso evento raro/fuori
hot-path di ogni altra decisione cognitiva del progetto.

Usa un provider LLM cloud separato (a scelta dell'operatore) da FreeLLM/Hermes
(locale, usato dai cittadini) — stesso identico pattern di record/replay di
llm/router.py.CognitiveRouter,
con un proprio trace_path cosi' la cache del sindaco non si mischia con quella dei
50 agenti.
"""
from __future__ import annotations

from llm.router import CognitiveRouter
from world.governance import Proposal


class MayorOffice:
    def __init__(self, router: CognitiveRouter, *, name: str = "Sindaco"):
        self.router = router
        self.name = name
        self.stats = {"rulings": 0, "ratified": 0, "vetoed": 0, "tie_breaks": 0}

    async def rule_on_proposal(
        self, tick: int, prop: Proposal, *, yes: int, no: int, abstain: int
    ) -> dict:
        """Ritorna {"final": bool, "choice", "thought", "confidence", "tie_break"}.

        `final` e' l'esito che world/governance.py applica poi in modo puro:
        True = la proposta passa (active_rules aggiornato), False = respinta.
        Pareggio (yes == no): il sindaco decide lui, voto decisivo.
        Altrimenti: ratifica (asseconda il voto popolare) o veto.

        Contratto col chiamante (engine/tick_engine.py): va invocato SOLO per
        proposte con yes >= no. Una proposta gia' respinta a maggioranza
        (no > yes) non va qui — il sindaco ha potere di ratifica/tie-break,
        non di ribaltare un rigetto popolare."""
        tie = yes == no
        choices = ["yes", "no"] if tie else ["ratify", "veto"]
        system = (
            f"Sei {self.name}, il sindaco eletto di Civitas, una città virtuale "
            "che studia web design con l'ambizione Awwwards Site of the Day. "
            + (
                "Il voto cittadino su questa proposta e' in PAREGGIO: hai il voto "
                "decisivo, decidi tu se passa (yes) o no (no)."
                if tie
                else "Una proposta ha gia' superato il voto cittadino a maggioranza. "
                "Puoi ratificarla o vetarla se ritieni che danneggi la citta'."
            )
            + " Rispondi SOLO in JSON con choice/thought/confidence, thought breve "
            "e motivato nell'interesse della città."
        )
        ctx = {
            "proposal_id": prop.proposal_id,
            "kind": prop.kind,
            "payload": prop.payload,
            "proposer_id": prop.proposer_id,
            "yes": yes,
            "no": no,
            "abstain": abstain,
        }
        d = await self.router.decide(
            agent_id="mayor",
            tick=tick,
            event="mayor_tie_break" if tie else "mayor_ratification",
            choices=choices,
            system_prompt=system,
            context=ctx,
        )
        if tie:
            final = d.choice == "yes"
            self.stats["tie_breaks"] += 1
        else:
            final = d.choice == "ratify"
            self.stats["ratified" if final else "vetoed"] += 1
        self.stats["rulings"] += 1
        return {
            "final": final,
            "choice": d.choice,
            "thought": d.thought,
            "confidence": d.confidence,
            "tie_break": tie,
        }
