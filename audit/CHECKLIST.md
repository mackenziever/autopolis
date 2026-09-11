# CHECKLIST DI ACCETTAZIONE

## Core
- [x] 50 agenti configurabili.
- [x] Tick rate configurabile 10–20 Hz.
- [x] Ordine update stabile.
- [x] Seed globale.
- [x] FSM senza LLM nel movimento.
- [x] A* e cache percorsi.
- [x] Collision reservation deterministica.
- [x] Bisogni: energia/fame/denaro.
- [x] Corsi, esami, skill e lavoro same-day.
- [x] Relazioni e conversazioni da prossimità.
- [x] Riflessione durante REST.

## Telemetria
- [x] Registro append-only MessagePack.
- [x] Header/schema/fingerprint.
- [x] Snapshot, movimenti, transizioni e pensieri.
- [x] Lettore con rilevazione troncamento.
- [x] SHA-256 e confronto determinismo.
- [x] Parquet offline opzionale.
- [x] PUB ZMQ derivato opzionale.
- [x] Delta snapshot / keyframe opzionale.
- [x] Manifest operativo del run (sidecar JSON).
- [x] Firma HMAC sidecar dei replay.

## LLM
- [x] Routing compatibile con il formato chat-completion standard via LiteLLM.
- [x] Semaphore e timeout.
- [x] Allow-list delle scelte.
- [x] Fallback stabile.
- [x] Trace record/replay.
- [x] Test integrazione mock compatibile con il formato chat-completion standard HTTP.
- [x] Budget token e contabilità costi.
- [x] Gateway TLS/Auth + rate-limit (`security/llm_gateway.py`).
- [x] Sanitizzazione PII su prompt/context/thought.
- [x] FreeLLMAPI Docker profile `llm` + CLI `--llm-api-base` / env.
- [x] Alveare RAG (`knowledge/`, batch fine-tick, FROZEN_STORE, chunk trace).
- [x] Mock LLM CI senza GHCR.
- [ ] Smoke/live contro server reale in produzione.

## Frontend
- [x] Viewer 2D separato.
- [x] Play/pausa/scrub/velocità.
- [x] Ostacoli, POI, agenti e legenda.
- [x] Client 3D Three.js (`viewer/viewer_3d.html`).
- [x] Interpolazione trail e raycast tooltip.
- [x] LOD distanza-camera (auto/high/low).
- [x] Test browser automatizzati (`tests/e2e`, Playwright).

## Produzione
- [x] Dockerfile e Compose con healthcheck.
- [x] Audit qualità/prestazioni/sicurezza/runbook.
- [x] Test core passanti.
- [x] Checkpoint/recovery atomico.
- [x] Observability Prometheus `/metrics` + `/health` + `/ready`.
- [x] OTel-lite span export (`metrics/otel.py`).
- [x] CI/CD GitHub Actions.
- [x] Lockfile piattaforma-specifico.
- [x] SBOM CycloneDX-like.
- [x] CVE scan script (`scripts/scan_cve.py` + CI).
- [x] Input validation + secret masking + rate limiter.
- [x] Rate-limit rete su metrics server e gateway LLM.
- [x] Hardening ZMQ (loopback-only + HMAC opzionale).
- [x] Ops bridge layer (`ops/civitas_ops.py`, fuori dal tick).
- [x] Load harness ≥1M tick + golden spatial / contratto Rust.
- [x] Cognitive worker opzionale + metriche overrun/cache/bytes.
- [ ] Retention/compaction Alveare (backlog).
- [ ] Scansione CVE continua in registry esterno (oltre pip-audit CI).
