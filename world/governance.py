"""Governance/voting deterministico tra agenti — parity con reel Civitas
(un agente propone una regola, la citta' vota, a volte anche lui vota contro).

Nessun LLM nella chiusura/tally: e' pura funzione deterministica sui voti
raccolti. La decisione di proporre/votare (LLM, evento raro) resta in
agents/state_machine.py + agents/self_improve.py, fuori dal tick hot-path
del movimento — stesso pattern di world/construction.py.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# kind -> (payload_key, default_value, description). Il valore di default e'
# quello che il mondo usa finche' nessuna proposta dello stesso kind passa;
# un secondo passaggio sovrascrive il precedente (ultima ordinanza vince).
PROPOSAL_CATALOG: Dict[str, Dict[str, Any]] = {
    "overcrowding_limit": {
        "payload_key": "max_agents_per_poi",
        "default_value": 999,
        "description": "Limite massimo di agenti contemporaneamente in un POI",
    },
    "noise_fine": {
        "payload_key": "noise_fine_amount",
        "default_value": 0.0,
        "description": "Multa (in crediti) per rumore/comportamento molesto",
    },
    "relocate_approval": {
        "payload_key": "relocate_requires_vote",
        "default_value": False,
        "description": "Se true, spostare un POI pubblico richiede prima una proposta approvata",
    },
}

PROPOSAL_COST = 15.0
VOTING_DURATION_DAYS = 2
MAX_ACTIVE_PROPOSALS = 3


@dataclass
class Proposal:
    proposal_id: str
    proposer_id: str
    kind: str
    payload: Dict[str, Any]
    submitted_tick: int
    closes_tick: int
    escrow_deposit: float
    status: str = "active"  # active | passed | rejected
    votes: Dict[str, str] = field(default_factory=dict)  # voter_id -> yes|no|abstain

    def as_dict(self) -> dict:
        d = asdict(self)
        d["yes"] = sum(1 for v in self.votes.values() if v == "yes")
        d["no"] = sum(1 for v in self.votes.values() if v == "no")
        d["abstain"] = sum(1 for v in self.votes.values() if v == "abstain")
        return d


class GovernanceBoard:
    def __init__(self, seed: int = 42, day_length: int = 600):
        self.seed = seed
        self.day_length = day_length
        self.proposals: Dict[str, Proposal] = {}
        self.active_rules: Dict[str, Any] = {
            spec["payload_key"]: spec["default_value"] for spec in PROPOSAL_CATALOG.values()
        }
        self.stats = {"proposed": 0, "passed": 0, "rejected": 0, "votes_cast": 0}

    # -- lettura -----------------------------------------------------------
    def open_proposals(self) -> List[Proposal]:
        return sorted(
            (p for p in self.proposals.values() if p.status == "active"),
            key=lambda p: p.proposal_id,
        )

    def proposals_closing_now(self, tick: int) -> List[Proposal]:
        """Proposte attive gia' scadute, in ordine deterministico — sola lettura,
        usata dal chiamante (engine/tick_engine.py) per interpellare il sindaco
        PRIMA di chiudere il tick con tick_day() (che resta puro/deterministico)."""
        return sorted(
            (p for p in self.proposals.values() if p.status == "active" and tick >= p.closes_tick),
            key=lambda p: p.proposal_id,
        )

    def rule(self, payload_key: str, default: Any = None) -> Any:
        return self.active_rules.get(payload_key, default)

    @staticmethod
    def tally(prop: Proposal) -> Tuple[int, int, int]:
        yes = sum(1 for v in prop.votes.values() if v == "yes")
        no = sum(1 for v in prop.votes.values() if v == "no")
        abstain = sum(1 for v in prop.votes.values() if v == "abstain")
        return yes, no, abstain

    # -- proposta ------------------------------------------------------------
    def _pid(self, proposer: str, kind: str, day: int) -> str:
        raw = f"{self.seed}:{proposer}:{kind}:{day}"
        return "prop_" + hashlib.sha256(raw.encode()).hexdigest()[:12]

    def can_propose(self, agent_id: str, kind: str, money: float) -> Tuple[bool, str]:
        if kind not in PROPOSAL_CATALOG:
            return False, "unknown_kind"
        if money + 1e-9 < PROPOSAL_COST:
            return False, "insufficient_funds"
        if any(p.proposer_id == agent_id and p.status == "active" for p in self.proposals.values()):
            return False, "proposer_has_active_proposal"
        if len(self.open_proposals()) >= MAX_ACTIVE_PROPOSALS:
            return False, "max_active_proposals"
        return True, "ok"

    def propose(
        self,
        *,
        tick: int,
        day: int,
        proposer_id: str,
        kind: str,
        runtime_money: float,
        value: Any = None,
    ) -> Tuple[Optional[Proposal], float, Optional[dict]]:
        """Deposita PROPOSAL_COST (non rimborsabile) e apre la votazione."""
        ok, reason = self.can_propose(proposer_id, kind, runtime_money)
        if not ok:
            return None, runtime_money, {
                "type": "proposal_reject",
                "tick": tick,
                "agent_id": proposer_id,
                "kind": kind,
                "reason": reason,
            }
        spec = PROPOSAL_CATALOG[kind]
        payload = {spec["payload_key"]: value if value is not None else spec["default_value"]}
        pid = self._pid(proposer_id, kind, day)
        closes_tick = tick + VOTING_DURATION_DAYS * self.day_length
        prop = Proposal(
            proposal_id=pid,
            proposer_id=proposer_id,
            kind=kind,
            payload=payload,
            submitted_tick=tick,
            closes_tick=closes_tick,
            escrow_deposit=PROPOSAL_COST,
        )
        self.proposals[pid] = prop
        self.stats["proposed"] += 1
        new_money = round(runtime_money - PROPOSAL_COST, 3)
        ev = {
            "type": "proposal_submitted",
            "tick": tick,
            "agent_id": proposer_id,
            "proposal_id": pid,
            "kind": kind,
            "payload": dict(payload),
            "closes_tick": closes_tick,
            "thought": f"Propongo {kind} ({payload}). Vediamo se la citta' e' d'accordo.",
        }
        return prop, new_money, ev

    # -- voto ----------------------------------------------------------------
    def cast_vote(self, *, tick: int, proposal_id: str, voter_id: str, vote: str) -> Optional[dict]:
        if vote not in ("yes", "no", "abstain"):
            return None
        prop = self.proposals.get(proposal_id)
        if prop is None or prop.status != "active":
            return None
        if voter_id in prop.votes:
            # Idempotente: il primo voto valido vince, i successivi sono ignorati.
            return None
        prop.votes[voter_id] = vote
        self.stats["votes_cast"] += 1
        return {
            "type": "vote_cast",
            "tick": tick,
            "agent_id": voter_id,
            "proposal_id": proposal_id,
            "vote": vote,
        }

    # -- chiusura --------------------------------------------------------------
    def tick_day(
        self, day: int, tick: int, *, mayor_rulings: Optional[Dict[str, dict]] = None
    ) -> List[dict]:
        """Chiude le proposte scadute in ordine deterministico (proposal_id).

        `mayor_rulings` (opzionale, retrocompatibile): proposal_id -> ruling del
        sindaco (agents/mayor.py.MayorOffice.rule_on_proposal, gia' calcolato dal
        chiamante PRIMA di questa chiamata — questo metodo resta puro, nessun I/O/
        LLM qui dentro). Se assente (sindaco disabilitato/non configurato), il
        comportamento e' identico a prima: yes > no decide, pareggio = non passa."""
        mayor_rulings = mayor_rulings or {}
        events: List[dict] = []
        for prop in sorted(self.proposals.values(), key=lambda p: p.proposal_id):
            if prop.status != "active" or tick < prop.closes_tick:
                continue
            yes, no, abstain = self.tally(prop)
            ruling = mayor_rulings.get(prop.proposal_id)
            passed = ruling["final"] if ruling is not None else (yes > no)
            prop.status = "passed" if passed else "rejected"
            if ruling is not None:
                events.append(
                    {
                        "type": "mayor_ruling",
                        "tick": tick,
                        "agent_id": "mayor",
                        "proposal_id": prop.proposal_id,
                        "kind": prop.kind,
                        "tie_break": ruling["tie_break"],
                        "choice": ruling["choice"],
                        "final": ruling["final"],
                        "confidence": ruling.get("confidence", 0.0),
                        "thought": ruling["thought"],
                    }
                )
            if passed:
                self.active_rules.update(prop.payload)
                self.stats["passed"] += 1
            else:
                self.stats["rejected"] += 1
            events.append(
                {
                    "type": "proposal_closed",
                    "tick": tick,
                    "proposal_id": prop.proposal_id,
                    "kind": prop.kind,
                    "result": prop.status,
                    "yes": yes,
                    "no": no,
                    "abstain": abstain,
                    "payload": dict(prop.payload) if passed else None,
                    "thought": (
                        f"Proposta {prop.kind} di {prop.proposer_id}: {prop.status} "
                        f"({yes} si, {no} no, {abstain} astenuti)."
                    ),
                }
            )
        return events

    def to_state(self) -> dict:
        """Stato grezzo per checkpoint (round-trip fedele, non il display snapshot())."""
        return {
            "proposals": {pid: asdict(p) for pid, p in self.proposals.items()},
            "active_rules": dict(self.active_rules),
            "stats": dict(self.stats),
        }

    def load_state(self, state: dict) -> None:
        self.proposals = {
            pid: Proposal(**{**p, "votes": dict(p.get("votes") or {})})
            for pid, p in (state.get("proposals") or {}).items()
        }
        self.active_rules.update(state.get("active_rules") or {})
        self.stats.update(state.get("stats") or {})

    def snapshot(self) -> dict:
        return {
            "proposals": [p.as_dict() for p in self.proposals.values()],
            "active_rules": dict(self.active_rules),
            "stats": dict(self.stats),
            "catalog": {k: v["description"] for k, v in PROPOSAL_CATALOG.items()},
        }
