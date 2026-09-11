# INDICE DELL'AUDIT

Audit eseguito il **7 settembre 2026**.

## Stato complessivo
`PASS_WITH_PRODUCTION_GAPS`

Il core è stato compilato, testato e sottoposto a due run equivalenti.
**P0+P1+P2 chiusi:** checkpoint, budget, metrics/health, security hardening,
CI/SBOM/lockfile, spatial hash, delta log, viewer 3D+LOD, load harness 1M,
golden spatial + contratto Rust, cognitive worker ops. Lacune residue: TLS edge
LLM gestito, smoke LLM produzione, CVE registry Docker, TTFT LLM, property FSM.

## Evidenze incluse
- `runtime/compile.json`
- `runtime/tests.json`
- `runtime/simulation_a.json`
- `runtime/simulation_b.json`
- `runtime/determinism.json`
- `runtime/inspect.json`
- `runtime/summary.json`

## Risultati principali
- 4 test superati, 0 falliti.
- 50 agenti, 600 tick.
- 30.000 snapshot.
- determinismo byte-per-byte: PASS.
- compute p95 osservato: 7,643 ms/tick.
- budget a 20 Hz: 50 ms/tick.

Le misure valgono per l'ambiente documentato e con LLM disabilitato.

## Inventario gap confermato
Elenco completo di ciò che manca (checklist, test, security, scale, fuori scope)
e priorità P0/P1/P2: vedi `GAP_INVENTORY.md`.
