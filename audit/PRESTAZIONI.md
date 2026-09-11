# AUDIT PRESTAZIONI E CAPACITÀ

## Critical path
Per tick: aggiornamento ordinato degli agenti, A*/cache se necessario, sistemi
sociali, serializzazione MessagePack e scrittura buffered. Le chiamate LLM non
sono necessarie per le routine.

## Budget
- 10 Hz: 100 ms/tick.
- 15 Hz: 66,67 ms/tick.
- 20 Hz: 50 ms/tick.
- Misura p95 locale: 7,643 ms/tick con 50 agenti, LLM-off.

## Collo di bottiglia atteso
1. Ricerca tutte-le-coppie O(N²), irrilevante a N=50 ma non a migliaia.
2. Snapshot completo ogni tick: crescita del log lineare con agenti × tick.
3. A* Python se la mappa o la popolazione aumentano molto.
4. Esportazione Parquet se erroneamente inserita nel tick.
5. LLM se atteso sincronicamente nel percorso autorevole.

## Soglie per ottimizzare
- Portare spatial in Rust solo se compute p95 supera il 40% del budget.
- Usare spatial hashing/k-d tree quando N rende O(N²) misurabilmente dominante.
- Delta snapshot o keyframe quando la telemetria supera i limiti disco/rete.
- Separare un cognitive worker process se le decisioni live aumentano.

## Metriche da raccogliere
- `tick_compute_seconds` histogram (`civitas_tick_seconds`).
- tick overrun count (`civitas_tick_overruns_total`, `result.perf.overruns`).
- agent update time per sistema.
- log bytes (`result.perf.log_bytes`, gauge `civitas_log_bytes`).
- path cache hit ratio (`result.perf.path_cache`).
- queue depth cognitiva (`CognitiveWorker.stats` se `--cognitive-worker`).
- LLM TTFT, latency, input/output token e error rate.
- VRAM used, KV-cache occupancy e batching efficiency.
- dropped live frames.

## Scale / P2
- Load: `python scripts/load_test.py --ticks 1000000 --agents 5 --spatial-hash`
  - Evidenza locale 2026-09-10: **PASS** 1M tick in ~182 s (~5486 Hz wall), p95 compute ~0.32 ms, overrun 16, log ~511 MB (delta on).
- Spatial backend: `--spatial-backend rust` (fallback Python se manca `civitas_spatial`; vedi `native/README.md`)
- Golden: `pytest tests/test_spatial_golden.py`
- Viewer LOD: `viewer/viewer_3d.html` select LOD auto/high/low
