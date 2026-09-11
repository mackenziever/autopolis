"""Schemi strutturati e convalida severa delle decisioni cognitive."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Iterable

@dataclass(frozen=True)
class Decision:
    choice: str
    thought: str
    confidence: float = 0.5
    # "live" (risposta LLM reale, appena calcolata o riletta da cache), "fallback"
    # (deterministico, nessun LLM coinvolto) o "unknown" (voce di cache pre-esistente
    # scritta prima che questo campo esistesse). Tag fissato una volta alla prima
    # scrittura nel trace e persistito: stabile per rid a prescindere da quante volte
    # o in quali run viene riletto -> non dipende da contatori globali mutabili
    # (bugfix determinismo, vedi llm/router.py.decide()).
    source: str = "unknown"
    # Request id (llm/router.py._id()) che ha originato questa decisione —
    # approfondimento RSI (2026-09-11): chiude il loop di audit fra una
    # lezione/scoperta scritta nel vault (knowledge/vault_librarian.py) e la
    # richiesta LLM esatta che l'ha prodotta, invece di doverlo ricostruire a
    # mano com'e' servito per il bug budget/contaminazione corretto oggi.
    rid: str = ""

    @classmethod
    def parse(cls, obj: Any, allowed: Iterable[str], source: str = "unknown", rid: str = "") -> "Decision":
        if not isinstance(obj, dict): raise ValueError("LLM output non e' un oggetto")
        allowed = list(allowed)
        choice = str(obj.get("choice", ""))
        if choice not in allowed: raise ValueError(f"choice non ammessa: {choice}")
        thought = str(obj.get("thought", ""))[:400].strip() or "Decisione senza commento."
        try: confidence = min(1.0, max(0.0, float(obj.get("confidence", .5))))
        except Exception: confidence = .5
        src = str(obj.get("source") or source or "unknown")
        rid_val = str(obj.get("rid") or rid or "")
        return cls(choice, thought, confidence, src, rid_val)
