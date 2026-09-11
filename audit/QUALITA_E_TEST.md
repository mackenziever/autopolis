# AUDIT QUALITÀ — RISULTATI EVIDENZE

Data audit: 7 settembre 2026

## Ambiente di verifica
- Interprete Python disponibile nel runner locale.
- Esecuzione senza rete e senza server LLM.
- Backend memoria fallback NumPy.
- Event loop asyncio standard se uvloop non installato.

## Comandi eseguiti
```bash
PYTHONDONTWRITEBYTECODE=1 python -m py_compile $(find . -name '*.py' -type f)
PYTHONDONTWRITEBYTECODE=1 pytest -q
python main.py --agents 50 --ticks 600 --fast --log data/run_a.msgpack
python main.py --agents 50 --ticks 600 --fast --log data/run_b.msgpack
python check_determinism.py data/run_a.msgpack data/run_b.msgpack
python inspect_replay.py data/run_a.msgpack
```

## Esito
- Compilazione sintattica: PASS.
- Test automatici: **4 passed**.
- Determinismo byte-per-byte: **PASS**.
- SHA-256 di entrambi i replay: `5adfe292881a88d1bc26d00d2b2c85b4c04b6a92e6ae7da56652d8e7ff7a77a5`.
- 50 agenti × 600 tick = **30.000 snapshot**.
- Esami: **32**.
- Cambi lavoro same-day: **12**.
- Conversazioni: **1.569**.
- Movimenti: **10.354**.
- Attese per prenotazione cella: **4.068**.
- Riflessioni: **50**.

## Prestazioni misurate
- Tempo wall headless: `1,2923 s` per 600 tick.
- Throughput headless: `464,28 tick/s`.
- Compute medio: `2,153 ms/tick`.
- Compute p95: `7,643 ms/tick`.
- Budget a 20 Hz: `50 ms/tick`.
- Margine p95 osservato: circa `6,5×` rispetto al budget a 20 Hz.

Questi numeri riguardano l'ambiente di audit e la modalità LLM-off. Non sono una
garanzia per hardware, modello o carichi differenti.

## Copertura attuale dei test
1. A* raggiunge il goal e usa solo celle attraversabili.
2. Replay byte-identico per seed/config equivalenti.
3. Conteggio snapshot uguale ad agenti × tick.
4. Seed differenti producono replay differenti.
5. Router LLM: live mock → trace → replay senza seconda chiamata.
6. Budget token: deny dopo limite agente e fallback tracciato.
7. Output LLM non valido → fallback + persistenza trace.
8. Mock HTTP compatibile con il formato chat-completion standard (`/v1/chat/completions`) end-to-end.
9. Checkpoint: resume allinea lo stato finale al run ininterrotto.
10. Checkpoint corrotto / fingerprint mismatch rifiutati.
11. Replay troncato: strict raise, tolerant recupera frame completi.
12. Frame con dimensione irragionevole rifiutato.

## Gap di test
- Smoke LLM contro server reale (script `llm_smoke_test.py`, ambiente esterno).
- Property testing della FSM.
- Load test multi-giorno ≥ 1 milione di tick.
- Test viewer automatizzati.
- Golden test di un futuro backend Rust.
