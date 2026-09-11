# RUNBOOK OPERATIVO

## Avvio rapido
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --agents 50 --ticks 600 --hz 15
python inspect_replay.py data/simulation_replay.msgpack
```

## Living City perpetua
Città perpetua: ogni agente ha un proprio kernel cognitivo persistente (FreeLLM free-tier + opz. Hermes locale).

```powershell
# Org board: ops/COMPANY.md
pwsh -File D:\AETHER\scripts\start-hermes-llm.ps1 -Profile coder -Layout mono-coder
python -m living_server --agents 12 --fast
# oppure LLM locale diretto (bypass catalog FreeLLM custom):
python -m living_server --agents 12 --fast --hermes
# Panel http://127.0.0.1:9300/ · /health · /v1/agents · WS /ws/city
# Smoke: python -m living_server --agents 4 --fast --max-ticks 120 --no-llm
docker compose --profile llm up -d living
$env:FREELLM_PASSWORD='…'
python scripts/register_local_hermes_freellm.py --model qwable-9b
```

Dettagli: `vault/01-AGENTS/agi-os-living.md` · `vault/06-MEMORY/wiki/city-self-build.md`.

## Città autocostruita

Due motori: **escrow agente** (Cafe come reel Civitas) + growth collettivo.
Un consulente esterno può proporre blueprint JSON extra (vedi
`scripts/apply_external_blueprint.py`).

```powershell
python -m living_server --agents 12 --fast --hermes
# GET /v1/city → growth + construction (escrow projects)
# apply-only: python scripts/apply_external_blueprint.py --from path/to/proposal.log
```

## Test e benchmark
```bash
pytest -q
python benchmark.py --agents 50 --ticks 5000
python scripts/load_test.py --ticks 1000000 --agents 5 --spatial-hash
# CI smoke load (10k): incluso in pytest; 1M: pytest -q -m slow
```

## Paperclip-city (task board locale)
Control plane leggero per coordinare job cognitivi (`reflect`, `career`, `study`, `social`)
senza cloud esterno. Persistenza in `data/paperclip_city/issues.jsonl`; ID deterministici
(`seed+agent+day+kind`). Il movimento FSM resta LLM-free; FreeLLM solo via `--llm`.

```powershell
# Smoke 50 tick con board attiva
python main.py --fast --paperclip-city --agents 5 --ticks 50

# Con metriche /health (paperclip_open, paperclip_done)
python main.py --fast --paperclip-city --metrics --agents 5 --ticks 50
```

Issue create a ogni boundary di giorno simulato; completate quando l'agente esegue
reflect/career/study/social nel FSM. Con `--llm --cognitive-worker` il heartbeat può
prefetch job LLM in coda (opzionale).

## Scale P2
```bash
python main.py --fast --spatial-hash --spatial-backend python --delta-log --cognitive-worker
python -m http.server 8080 -d viewer   # viewer_3d.html con LOD
```

## FreeLLMAPI ambiente completo
Import di chiavi provider da un `.env` esterno esistente:

```powershell
$env:FREELLM_PASSWORD='…'
python scripts/import_v12_keys_to_freellm.py --env "/path/to/existing/.env"
```

## FreeLLMAPI + Alveare (profile llm) — apparato agenti REALE
Single-user: bind solo su `127.0.0.1`. Non esporre in LAN.

FreeLLMAPI aggrega i free tier (Groq, Google, Mistral, OpenRouter, …) dietro un solo
`/v1` compatibile con il formato chat-completion standard. Gli agenti Civitas decidono su eventi rari (reflect,
career, study, social), scrivono lesson in Alveare e aggiornano focus/corso/lavoro.
Il movimento resta deterministico (no LLM nel hot-path).

```powershell
# Bootstrap Windows (crea .env.freellmapi, avvia freellmapi+alveare+opz. simulator-llm)
.\scripts\bootstrap_freellm_stack.ps1

# Manuale:
# 1) chiave encryption
copy .env.freellmapi.example .env.freellmapi
# 2) stack cognitivo
docker compose --profile llm up -d --build
# Dashboard FreeLLM: http://127.0.0.1:3001
#   → Keys: aggiungi provider free-tier
#   → copia unified key → $env:CIVITAS_LLM_API_KEY='freellmapi-...'
# Alveare: http://127.0.0.1:9200/health
# Simulator LLM metrics: :9101

# Host run (dopo key):
$env:CIVITAS_LLM_API_BASE='http://127.0.0.1:3001/v1'
$env:CIVITAS_LLM_MODEL='auto'
$env:CIVITAS_ALVEARE_URL='http://127.0.0.1:9200'
python main.py --fast --llm --cognitive-worker --agents 8 --ticks 600 `
  --alveare-url http://127.0.0.1:9200 --log data/simulation_replay_llm.msgpack
```

Eventi trace attesi con `--llm`: `reflection` (+focus/lesson), `career_decision`,
`study_decision`, `social_decision`, `exam_result`, `job_change`.
Senza API key / provider upstream → fallback deterministico (sim continua, non è “live”).

### Contratto embedding / replay
- Default offline: **embedder hash** (deterministico). Il replay offline verifica il *wiring* RAG, non la qualità semantica del retrieval.
- Con `CIVITAS_EMBED_MODEL` impostato, Alveare prova `POST {api_base}/embeddings`. Per stabilità cross-arch, arrotondare i float a **6 decimali** lato provider o normalizzare nel client.
- `CIVITAS_REPLAY=1` o `CIVITAS_ALVEARE_FROZEN=1`: store **FROZEN** (upsert/ingest → 423). Il retrieval in `reflect`/`decide` riusa i **chunk di testo completi** dal `llm_trace.jsonl`, indipendenti dallo store live.
- Upsert agenti: **batch a fine tick**, ordinati per `(tick, agent_id, text)`.

### Ops bridge — Alveare
```bash
python ops/civitas_ops.py alveare-query --text "studio coding"
python ops/civitas_ops.py alveare-ingest --vault /path/to/vault
```

## E2E viewer (Playwright)
```bash
pip install "playwright>=1.40"
python -m playwright install chromium
pytest -q tests/e2e --tb=short
```

## Ops bridge (audit/sim fuori dal tick)
```bash
python ops/civitas_ops.py audit
python ops/civitas_ops.py run --agents 50 --ticks 300 --spatial-hash --delta-log
```
Non entra mai nel hot-path del tick.

## Gateway LLM (TLS/Auth)
```bash
set CIVITAS_GATEWAY_TOKEN=...
python -m security.llm_gateway --listen 127.0.0.1:8443 \
  --upstream http://127.0.0.1:8000/v1 --token-env CIVITAS_GATEWAY_TOKEN
# opzionale TLS: --cert cert.pem --key key.pem
```

## Firma replay + manifest
```bash
set CIVITAS_REPLAY_HMAC_KEY=...
python main.py --fast --ticks 100 --sign-replay --manifest data/run_manifest.json
```

## Verifica riproducibilità
```bash
python main.py --fast --log data/a.msgpack
python main.py --fast --log data/b.msgpack
python check_determinism.py data/a.msgpack data/b.msgpack
```

## Viewer
Aprire `viewer/replay_viewer.html`, quindi selezionare il replay. Se il browser
blocca l'apertura locale, servire la cartella:
```bash
python -m http.server 8080 -d viewer
```

## Incidenti
### Tick overrun
1. Eseguire `benchmark.py`.
2. Disabilitare LLM/live feed.
3. Analizzare A*, pair proximity e logger.
4. Ridurre snapshot o passare a backend nativo solo dopo profilazione.

### LLM non raggiungibile
Il fallback mantiene la simulazione. Controllare `router.stats.errors`, endpoint,
modello e proxy. Non cancellare la trace valida.

### Replay troncato
Usare `iter_records(path, tolerate_truncated=True)` per recuperare tutti i frame
completi. Non modificare l'originale; crearne una copia riparata.

### Disco pieno
Arrestare in modo controllato, preservare il replay, liberare spazio e ripartire
da checkpoint.

## Checkpoint / recovery
Salvataggio periodico:

```bash
python main.py --agents 50 --ticks 600 --fast \
  --checkpoint data/simulation.checkpoint.msgpack \
  --checkpoint-every 100 \
  --log data/simulation_replay.msgpack
```

Ripresa (`--ticks` = tick finale assoluto, non tick aggiuntivi):

```bash
python main.py --agents 50 --ticks 1200 --fast \
  --resume data/simulation.checkpoint.msgpack \
  --log data/recovered.msgpack
```

Il checkpoint è MessagePack con SHA-256 del payload e fingerprint config.
Un file corrotto o un fingerprint incompatibile solleva `CheckpointError`.

## LLM budget e smoke
API key (mai in codice/prompt):

```bash
set CIVITAS_LLM_API_KEY=...
python llm_smoke_test.py --api-base http://localhost:8000/v1 --model nome-modello
```

## Backup
Conservare insieme: codice/versione Git, config, replay, llm trace, eventuale
checkpoint, manifest dipendenze e hash SHA-256.
