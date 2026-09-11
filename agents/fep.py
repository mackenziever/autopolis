"""Expected Free Energy per la scelta di postura giornaliera.

Porting mirato dello stesso Free Energy Principle di Friston (Active
Inference / Expected Free Energy) gia' implementato e verificato in
produzione in un altro progetto di ricerca personale. Il dominio cambia
(li' una scelta di azione con un segnale di rendimento, qui posture
giornaliere agente con un proxy di bisogno soddisfatto), ma la formula
resta la stessa:

    G(azione) = pragmatic_value + peso_epistemico * epistemic_value
    pragmatic_value  = -media(outcome storici)       (bassa se l'azione paga)
    epistemic_value  = std(outcome storici) / (std + 1)  (alta se incerta)

A differenza di `agents/cognitive.py._fep_posture_scores()` (stima statica
dal solo stato corrente, senza memoria), questa classe fa apprendere
l'agente dall'ESPERIENZA REALE: ogni giorno registra quanto la postura
scelta ieri ha davvero ridotto il bisogno che doveva soddisfare, e la scelta
di oggi tiene conto di quella storia. Pura aritmetica deterministica, mai
LLM/RNG; stato piccolo e serializzabile per il checkpoint.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List

OUTCOME_HISTORY = 20
EPISTEMIC_WEIGHT = 0.3


class PostureExperience:
    def __init__(self, postures: List[str], history: int = OUTCOME_HISTORY):
        self._postures = list(postures)
        self._history = history
        self._outcomes: Dict[str, Deque[float]] = {
            p: deque(maxlen=history) for p in self._postures
        }

    def record_outcome(self, posture: str, reward: float) -> None:
        """reward atteso in [-1, 1]: quanto la postura ha soddisfatto il bisogno
        che doveva coprire (1 = bisogno azzerato, -1 = peggiorato)."""
        if posture not in self._outcomes:
            self._outcomes[posture] = deque(maxlen=self._history)
        self._outcomes[posture].append(max(-1.0, min(1.0, reward)))

    def expected_free_energy(self, posture: str) -> float:
        """G(postura): piu' basso e' meglio (convenzione Friston)."""
        outcomes = list(self._outcomes.get(posture, ()))
        if not outcomes:
            return 0.0  # prior neutro: nessuna esperienza ancora
        mean_r = sum(outcomes) / len(outcomes)
        pragmatic = -mean_r
        if len(outcomes) > 1:
            var = sum((x - mean_r) ** 2 for x in outcomes) / len(outcomes)
        else:
            var = 1.0
        std = var ** 0.5
        epistemic = std / (std + 1.0)
        return pragmatic + EPISTEMIC_WEIGHT * epistemic

    def best_posture(self, candidates: List[str]) -> str:
        return min(candidates, key=lambda p: (self.expected_free_energy(p), p))

    def to_state(self) -> Dict[str, List[float]]:
        return {p: list(v) for p, v in self._outcomes.items()}

    def load_state(self, state: Dict[str, List[float]]) -> None:
        for p, values in (state or {}).items():
            self._outcomes[p] = deque(
                (max(-1.0, min(1.0, float(x))) for x in values), maxlen=self._history
            )
