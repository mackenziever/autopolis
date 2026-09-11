# SCOPO DEL PROGETTO

## Missione
Civitas Full Core simula una città abitata da 50 agenti autonomi, ciascuno con
persona, bisogni, lavoro, competenze, relazioni e memoria. Il sistema separa
rigorosamente lo stato autorevole dalla visualizzazione 2D/3D.

## Obiettivi verificabili
- 50 agenti attivi a 10–20 tick/s in modalità real-time.
- Routine ordinarie senza chiamate LLM per tick.
- Replay completamente ricostruibile da un registro append-only.
- Stesso codice/config/seed/decisioni esterne => stessi byte di replay.
- Corso, esame, skill unlock e assunzione nello stesso giorno simulato.
- Interazioni sociali emergenti da posizione e stato.
- Integrazione LLM opzionale, limitata, validata e registrata.
- Frontend sostituibile senza modificare il motore.

## Fuori dallo scope della baseline
- Fine-tuning online dei pesi.
- Fisica 3D autorevole.
- Grafica che influenza il mondo.
- Garanzia di determinismo delle API LLM non registrate.
- Database distribuito obbligatorio.

## Definizione di "autonomo"
Gli agenti non seguono una sequenza cinematografica pre-renderizzata: operano
attraverso FSM, bisogni, memoria, skill, relazioni e decisioni event-driven.
Restano tuttavia vincolati dalle regole e dal calendario progettati; pertanto il
termine corretto è simulazione deterministica ed emergente, non priva di regole.
