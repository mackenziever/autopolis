"""Escalation cognitiva a livelli di confidenza (Tier 0 euristico -> Tier 1 LLM).

Ispirato al pattern di routing multi-tier con circuit breaker usato in un
altro progetto di ricerca personale (sistema multi-provider live), ma
ridotto a 2 tier per Civitas: Tier 0 e' l'euristica deterministica gia'
esistente (sempre attiva di default, cap/decay come hard-case mining), Tier
1 e' la chiamata LLM vera,
attivata SOLO quando un segnale deterministico di incertezza supera una soglia.

Design rivisto dopo revisione di un consiglio esterno multi-modello (2026-09-10):
- Isteresi (soglia di ingresso > soglia di uscita): evita il flapping e
  l'"auto-lock" segnalato nel consiglio — se il gate si attiva su varianza alta e
  l'LLM viene raramente chiamato (budget/errori), la varianza resta alta per
  costruzione e il gate resterebbe acceso per sempre senza isteresi/cooldown.
- Cooldown dopo l'attivazione: forza un numero minimo di cicli Tier-0-only
  anche se il segnale resta alto, per dare tempo al ciclo di apprendimento
  (agents/fep.py) di aggiornarsi e ridurre naturalmente il segnale.
- Ogni output LLM resta un evento esterno cristallizzato nel trace del router
  (LLMTrace) PRIMA di toccare lo stato del mondo — l'escalation decide SOLO
  se tentare la chiamata live, mai cosa fare col suo risultato: il replay
  legge sempre il verdetto registrato, non lo ricalcola (stesso principio
  gia' in uso in llm/router.py.decide()).
"""
from __future__ import annotations

ENTER_THRESHOLD = 0.5
EXIT_THRESHOLD = 0.2
COOLDOWN_CYCLES = 2


class EscalationGate:
    def __init__(
        self,
        enter_threshold: float = ENTER_THRESHOLD,
        exit_threshold: float = EXIT_THRESHOLD,
        cooldown_cycles: int = COOLDOWN_CYCLES,
    ):
        self.enter_threshold = enter_threshold
        self.exit_threshold = exit_threshold
        self.cooldown_cycles = cooldown_cycles
        self._active = False
        self._cooldown_remaining = 0

    def decide(self, signal: float) -> bool:
        """signal in [0,1]: quanto e' incerta/critica la decisione corrente.
        Ritorna True se questo ciclo deve tentare il Tier 1 (LLM vera)."""
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            self._active = False
            return False
        if self._active:
            if signal <= self.exit_threshold:
                self._active = False
            return self._active
        if signal >= self.enter_threshold:
            self._active = True
            return True
        return False

    def note_cycle_result(self, escalated: bool) -> None:
        """Chiamare dopo ogni ciclo: forza un cooldown Tier-0-only dopo ogni
        escalation, cosi' il gate non resta bloccato acceso all'infinito."""
        if escalated:
            self._cooldown_remaining = self.cooldown_cycles

    @property
    def is_active(self) -> bool:
        return self._active

    def to_state(self) -> dict:
        return {"active": self._active, "cooldown_remaining": self._cooldown_remaining}

    def load_state(self, state: dict) -> None:
        state = state or {}
        self._active = bool(state.get("active", False))
        self._cooldown_remaining = int(state.get("cooldown_remaining", 0))
