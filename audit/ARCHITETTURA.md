# ARCHITETTURA E CONTRATTI

## Flusso autorevole
`config + seed -> tick engine -> FSM/world systems -> immutable event log`

## Flusso derivato
`event log / snapshot PUB -> viewer 2D o client Godot/Three.js`

## Cognizione
`evento raro -> memoria -> router -> trace replay | LLM live | fallback -> decisione validata`

## Contratti
1. Solo `CivitasEngine` orchestra le mutazioni durante il tick.
2. Gli agenti sono aggiornati in ordine crescente di ID.
3. Le celle sono riservate nello stesso ordine, rendendo stabile la collisione.
4. Il visualizzatore non invia comandi allo stato autorevole.
5. Il MessagePack è il registro canonico; Parquet è una vista analytics offline.
6. Gli output LLM live entrano nel determinismo solo dopo essere stati registrati.
7. Nessun tempo wall-clock è scritto nel replay canonico.
8. Tutti gli eventi hanno un `type`; gli eventi agent-specific includono `agent_id`.

## Eventi
- `state_transition`: cambio FSM.
- `move`: spostamento cella-cella.
- `wait`: collisione/prenotazione.
- `snapshot`: stato completo minimo per il replay.
- `exam_result`: risultato corso.
- `job_change`: assunzione/promozione.
- `conversation`: variazione relazione.
- `reflection`: aggiornamento strategia.

## Failure mode
- LLM irraggiungibile: fallback stabile, simulazione continua.
- USearch assente: ricerca vettoriale NumPy.
- uvloop assente: event loop asyncio standard.
- ZMQ assente/client lento: feed live disabilitato o frame scartato.
- Polars assente: solo esportazione Parquet non disponibile.
- ultimo frame troncato: lettore può operare in modalità tollerante.
