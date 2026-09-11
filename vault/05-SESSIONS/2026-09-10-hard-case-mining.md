---
tags: [autopolis, session, learning, hard-case-mining, council]
date: 2026-09-10
---

# Sessione 2026-09-10 — "sistemare il cervello dei cittadini"

Richiesta: dare ai cittadini compiti, auto-miglioramento reale, capacita' di
cercare/specializzarsi/studiare, sfruttamento delle API free-tier, ecosistema
vivente evolutivo, ottimizzazione del motore a layer.

## Diagnosi

- **Task/self-improve/study/search/storage**: gia' presenti (`paperclip_city`
  board, `agents/self_improve.py`, corsi→skill→lavoro, `knowledge/web_search.py`
  Stage 8, Alveare + vault). Nessuna azione necessaria qui.
- **Hard-case mining**: documentato in `06-MEMORY/wiki/self-learning-loop.md`
  ma **non implementato**: `agents/cognitive.py._retrieve_alveare` passava una
  query piatta senza peso per esito negativo; `reflect()` contava i fallimenti
  su `kind=="exam_failed"` ma `evaluate_exam` scriveva sempre `kind="exam"` —
  gli esami bocciati non venivano mai conteggiati. **Implementato in questa
  sessione** (vedi sotto).
- **FreeLLMAPI**: la chiave in `.env.llm` e' valida (`GET /v1/models` con
  header `Authorization: Bearer ...` risponde, non e' una chiave invalida).
  Il blocco reale e' un altro: su ~373 modelli in catalogo, ~292 non hanno
  nessuna key provider configurata e i restanti sono quasi tutti rate-limited
  in questo momento (`HTTP 429 "All models exhausted"` anche su `model:auto`).
  Il catalog `ops/council/models_catalog.yaml` ha inoltre id modello
  stale/non validi (`gemini-2.0-flash-exp`, `openai/auto`, ecc. → 404 "not in
  catalog"). Serve: aggiungere piu' provider key dalla dashboard FreeLLM
  (`http://127.0.0.1:3001/keys`) e allineare gli id nel catalog a quelli
  realmente instradabili da `/v1/chat/completions` (non basta comparire in
  `/v1/models`).
- **Agnes**: `ops/hermes_agnes.py` la descrive come profilo Hermes/Aether, non
  un servizio HTTP dedicato — coerente con quanto gia' noto, non richiede
  ulteriori azioni in questa sessione.

## Consiglio multi-AI (browser, claude-in-chrome)

Su richiesta esplicita, oltre al consiglio interno (`ops/council/`, bloccato
da FreeLLM come sopra) e' stato consultato in diretta via browser un secondo
consiglio esterno — Sakana (chat.sakana.ai), Kimi (kimi.ai), ChatGPT
(chatgpt.com), Qwen (chat.qwen.ai) — sulla stessa domanda: come implementare
hard-case mining deterministico e rendere l'ecosistema evolutivo restando
dentro il vincolo "LLM solo su eventi rari". Le quattro risposte sono
convergenti in modo indipendente su:

1. Ogni fallimento genera un contatore/tag **deterministico** (streak,
   `obstacle:<topic>`, `skill_gap:<skill>`) calcolato da FSM/contatori, mai
   dall'LLM.
2. Il punteggio di retrieval va pesato con un **moltiplicatore puro** dello
   streak (con **cap** e **decay temporale**) — mai iniettato dall'LLM.
3. Specializzazione per agente = profilo di competenza che cresce con i
   successi sui propri hard-case; trasmissione tra agenti solo **passiva**
   via Alveare condiviso (mai push attivo).
4. Metriche concrete convergenti: tempo/tentativi per risolvere lo stesso
   hard-case nel tempo, tasso di riuso lesson esistenti, distribuzione skill
   tra agenti.
5. **Rischio principale, citato da tutte e quattro**: "echo chamber"/feedback
   loop patologico — un fallimento ricorrente autoalimenta il proprio peso e
   monopolizza la cognizione dell'agente. Mitigazione condivisa: boost cap +
   decay deterministico + forzatura di novita'.

Trascrizioni complete nelle rispettive chat (non salvate qui per estensione;
sintesi sopra e' fedele a tutte e quattro le risposte).

## Implementato in questa sessione

- `agents/cognitive.py`: `hard_case_streak: Dict[str,int]` per agente (cap
  `HARD_CASE_STREAK_CAP=6`), `_record_hard_case_failure/_success`,
  `_hard_case_tags`, `_hard_case_query_suffix` (bias deterministico della
  query Alveare in `reflect()`), `_decay_hard_case_streaks()` (decadimento
  giornaliero di 1 per topic, chiamato a fine `reflect()`).
- `evaluate_exam`: bugfix `kind` (`"exam"` → `"exam_failed"`, ora contato
  correttamente da `reflect()`); salienza locale cresce con lo streak; testo
  della lesson include streak e skill_gap (il retrieval Alveare pesa sul
  *testo*, i tag non sono indicizzati dal server — vedi `knowledge/alveare_store.py.query`,
  che fa solo cosine-similarity su `text`).
- `agents/state_machine.py`: streak di collisioni consecutive (hot-path,
  solo contatore in memoria + salienza, **nessuna nuova chiamata di rete** per
  restare dentro il vincolo "LLM/IO mai nel movimento"); reset al primo passo
  libero.
- `engine/checkpoint.py`: `hard_case_streak` persistito in
  `_agent_dump`/`restore` (stesso pattern del bugfix Stage 6/7 su
  construction/governance/lessons — altrimenti il resume avrebbe divergenza).
- `engine/tick_engine.py`: `_health_extra()["hard_case_mining"]` (agenti con
  streak attivo, topic attivi totali, streak massimo) — artefatto osservabile
  live via `/health`, stesso pattern di governance/web_search stats.

## Verifica

`pytest -q` → 62 passed. Determinismo a doppio-run (seed=42, 50 agenti, 600
tick) → DETERMINISTIC, ma solo azzerando `data/llm_trace.jsonl` prima di
entrambe le run: la prima verifica (senza azzerare) dava MISMATCH, diagnosticato
come un **quarto bug di determinismo pre-esistente** (non introdotto in questa
sessione, non ancora corretto): `agents/cognitive.py.reflect()` decide se usare
`d.thought` o il `template` in base a `router.stats["replay"]`, che dipende da
cosa e' gia' cache-hit nel trace file condiviso tra run separate — stesso
seed/config/codice puo' quindi produrre byte diversi a seconda dello stato
pregresso di quel file. Dettagli e piano in `audit/GAP_INVENTORY.md` (sezione
"Gap residui").

## Round 2 — ricerca esterna (altri progetti personali, repo ATSMATRIX, consiglio FEP)

Su richiesta di analizzare alcuni altri progetti personali dell'utente e
di analizzare i repo del profilo GitHub `anyel1to` (link Instagram bio-link
incollato dall'utente) per idee applicabili al motore Autopolis:

- **Altro progetto personale (assistente cognitivo always-on)**: quasi nulla
  applicabile direttamente — dominio e modello di concorrenza troppo diversi
  da Autopolis (infrastruttura multi-container always-on vs single-process
  deterministico). Uniche idee generalizzabili (concetto, non codice):
  escalation a livelli di confidenza, backup-prima-di-mutazione (non
  applicabile oggi, nessuna mutazione di persona esiste), e un'idea concreta
  poi effettivamente portata: **Free Energy Principle / Active Inference**
  per la scelta della postura giornaliera.
- **agent-architecture-study**: NON riguarda motori di simulazione (e' ricerca
  su design del mio sistema di memoria/MCP tool) — nessun collegamento forzato.
- **Repo ATSMATRIX** (github.com/anyel1to): dashboard multi-agente
  single-file MIT (Canvas 60-120fps, force-directed physics per 200+ agenti;
  pattern "core-and-ring" con pacchetti di stato minimi tra worker
  specializzati invece di contesto pieno) — rilevante per viewer (dominio
  Cursor) e per lo scambio di stato tra fasi cognitive, non implementato ora.

**Secondo consiglio multi-AI** (Sakana/Kimi/ChatGPT/Qwen, stessa sera) su
librerie git reali per implementare i tre pattern trovati. Convergenza forte:
`infer-actively/pymdp` (MIT, 734 star, attivo — verificato anche via GitHub
API direttamente) e' la libreria Python di riferimento per Active Inference,
**ma tre risposte su quattro sconsigliano di dipenderne direttamente** in
Autopolis: dalla v1.0 pymdp usa un backend JAX (JIT/RNG) incompatibile col
requisito bit-per-bit-replay (segnalato indipendentemente da Sakana e
ChatGPT); calibrare le matrici per 50 agenti e' costoso e "sostituisce
un'euristica semplice con complessita' non sempre giustificata" (Sakana);
ChatGPT esplicitamente: *"pymdp si', come laboratorio matematico/prototipo,
non come dipendenza critica del replay engine — implementerei una versione
minimale Active-Inference-inspired con algebra deterministica controllata da
voi"*. Su quale pattern implementare per primo, 3/4 (Qwen, ChatGPT, e
implicitamente la cautela di Sakana) indicano l'escalation cognitiva a
livelli di confidenza come priorita' piu' alta (ROI immediato, nessuna nuova
dipendenza, riduce subito le chiamate LLM); solo Kimi mette Active Inference
al primo posto.

**Deciso e implementato in Round 3**: oltre al punteggio FEP, anche l'escalation cognitiva a
livelli di confidenza (`agents/escalation.py.EscalationGate`, isteresi ingresso/uscita +
cooldown post-attivazione, collegata a `llm/router.py.decide(escalate=...)` in modo
retrocompatibile) e i filtri multi-campo su Alveare (`tags`/`agent_id`/`tick_min`/`tick_max`,
pattern da `lancedb/vectordb-recipes` senza adottarne la dipendenza). Verificato:
`pytest -q` → 76 passed; determinismo a doppio-run (trace azzerato) → DETERMINISTIC, hash
identico alla run pre-escalation-gate.

**Punteggio deterministico ispirato a FEP**
(`AgentCognitiveEngine._fep_posture_scores()` in `agents/cognitive.py`) —
niente dipendenza pymdp, solo rapporti su contatori/stato locale gia'
disponibili (energia, fame, relazioni, `hard_case_streak`). Sostituisce la
scelta arbitraria (hash) del fallback del router **solo** quando la risposta
non viene da LLM live/replay (`used_live_or_replay == False`), lasciando
intatto il path LLM/replay esistente (nessuna regressione su trace gia'
registrate). Verificato con `pytest -q` + check di determinismo a doppio-run
(trace azzerato prima di entrambe le run).

**Aggiornamento Round 3 — implementato**: l'escalation cognitiva a livelli di
confidenza (sopra indicata come backlog ad alta priorita') e' stata
implementata: gate a 2 livelli (non i 7 tier del riferimento originale,
inadatti a un solo backend LLM reale), isteresi + cooldown per l'auto-lock
segnalato da Kimi, segnale = `hard_case_streak` normalizzato. Pattern
"core-and-ring" (pacchetti di stato minimi) resta backlog, terza priorita' —
refactoring dell'interfaccia, non richiede libreria, non affrontato in questa
sessione.

## Round 3 — porting FEP reale + bugfix join_crew (dati live da /v1/city)

Su segnalazione dell'utente ("noi lo avevamo sviluppato questo Free Energy
Principle" + "prendi tutto quello che era utile" da un altro progetto
personale): trovato ed esaminato codice reale
(`FristonFEP`/`PredictiveCodingEngine`, gradient descent su Free Energy
variazionale, `expected_free_energy`/`get_action_priors`/`update_action_outcome`)
e un modulo di routing multi-tier con circuit breaker. Il primo e' stato
portato in Autopolis (vedi sopra, `agents/fep.py`); il secondo resta backlog
di riferimento per l'escalation cognitiva.

**Repo ATSMATRIX (profilo github.com/anyel1to), completati tutti i 9 repo rilevanti**: oltre ai
4 gia' esaminati (VOXEL-YARD, NEXUS, AGENT-GRAPH, AGENT-RING), controllati anche AGENT-COMPOUND,
HORIZON, LEAD-SWARM e `atsmatrix-agent-visualizeR` (il piu' stellato, 18 stelle — visto anche
live: 500+ nodi in due cluster force-directed, pipeline collect→match→cross-link→verify→synth).
Nessuno usa Three.js/WebGL (tutti Canvas 2D single-file MIT). Unica idea genuinamente
trasferibile: il pattern cluster-layout a molla/momento orbitale + "fotoni" animati lungo gli
archi per rappresentare pacchetti dati tra agenti (da `atsmatrix-agent-visualizeR`) — adattabile
a una vista ausiliaria "debug/graph" nel viewer Three.js (separata dalla vista spaziale città),
con instanced particles al posto del canvas 2D, per mostrare propagazione di eventi cognitivi
rari tra agenti. AGENT-COMPOUND/HORIZON/LEAD-SWARM non offrono nulla di nuovo oltre a quanto
gia' trovato — dominio troppo diverso (finance) o tecnica gia' coperta.

Separatamente, l'utente ha condiviso uno snapshot live di
`http://127.0.0.1:9300/v1/city`: 16 rilocazioni proposte, solo 3 completate,
12 fallite con crew vuota. Diagnosi: `agents/self_improve.py.build_decision`
generava un'unica scelta generica `"join_crew"` — con piu' rilocazioni aperte
in parallelo, `world/construction.py.join_crew()` senza `project_id` prendeva
sempre `open_relocations()[0]`, quindi ogni tentativo di join finiva sullo
stesso (primo) progetto affamando tutti gli altri. **Corretto**: scelta
`join_crew_<project_id>` per rilocazione (stesso pattern gia' usato per
`propose_relocate_<poi>`), cosi' un agente puo' scegliere quale crew
rinforzare. Test dedicato in `tests/test_construction_escrow.py`.

## Round 4 — pubblicazione GitHub + valutazione 9 repo esterne + Alveare

**GitHub**: repo pubblicata (privata) su https://github.com/mackenziever/autopolis.
`.gitignore` esteso per escludere stato locale di tooling (`.claude-flow/`, `.swarm/`,
`ruvector.db`) non pertinente al progetto; verificato via scan pattern (nessun secret-like
match) prima del push, oltre alle esclusioni `.env*` gia' presenti.

**9 repo esterne segnalate dall'utente, valutate una per una (fork dedicati, non solo dal
nome)**: SamurAIGPT/Generative-Media-Skills, Mininglamp-AI/Mano-P, AutoArk/EVA-OS,
waybarrios/vllm-mlx, NVIDIA-AI-Blueprints/video-search-and-summarization,
gokayfem/awesome-vlm-architectures, Denis2054/Building-Business-Ready-Generative-AI-Systems,
Tencent/teamai-cli → **tutte "NO"** per integrazione diretta (dominio content-creation/GUI-VLA/
audio-OS-robotica/CCTV-surveillance/bibliografia-VLM/didattica-libro/config-sync-team-umani,
o hardware incompatibile — vllm-mlx e' Apple Silicon-only, l'utente ha Windows/RTX4090). Il
capitolo "Trajectory Analysis" del libro Packt e' un utile controesempio: usa GPT-4o per
interpolare traiettorie, l'opposto della FSM deterministica di Autopolis.

**Unica eccezione: `lancedb/vectordb-recipes`** — non adottare la dipendenza (costo/beneficio
sfavorevole per poche migliaia di chunk, romperebbe l'auditabilita' JSONL), ma il pattern si':
filtri multi-campo (`tags`/`agent_id`/`tick`-range) combinati con la similarity search.
**Implementato** in `knowledge/alveare_store.py.query()` + `server.py` + `client.py`, senza
nuova dipendenza, stesso embedder deterministico. Rende potenzialmente utilizzabili i tag
`hard_case`/`obstacle:*`/`skill_gap:*` gia' scritti dall'hard-case mining — capacita' aggiunta,
non ancora usata da `_retrieve_alveare` (nessun cambio di comportamento per il codice esistente,
wiring dei chiamanti lasciato come prossimo passo separato). Test in `tests/test_alveare_store.py`.

## Round 5 (2026-09-11) — component_intel → Alveare, ricerca web, fix concorrenza

Richiesta utente: *"collega il database component_intel ad Alveare e dagli la possibilità
di cercare su internet e utilizzare in modalità ospite altre ai per migliorarsi e
immagazzinare tutto"* + nota esplicita di preferenza: *"consiglierei di utilizzare il
disco per immagazzinare le informazioni nuove"*.

**component_intel** (Postgres reale, container Docker `aether-vault-db-1`, schema
`component_intel` — non nello stack docker-compose di Autopolis, e' l'infrastruttura
Aether Studio dell'utente, gia' nota da [[aether-postgres-schemas]] in memoria persistente)
verificato vivo (`docker ps`) e ispezionato: 4 tabelle, 9 `kind` diversi, il piu' ricco
`awwwards_site` (3274 righe, score reale + studio + url + tag Awwwards autentici come
"WebGL"/"GSAP"/"Interaction Design"). Collegato ad Alveare con
`scripts/ingest_component_intel.py` (924 chunk: siti score≥7.5 + interaction pattern +
dossier), scritto su disco tramite l'HTTP upsert del server Alveare gia' in esecuzione
(mai scrittura diretta sul file — il container resta l'unico writer di
`data/alveare/chunks.jsonl`, coerente con la preferenza "disco" dell'utente e con
l'architettura single-writer del progetto).

Durante l'ingest bulk, il traffico concorrente del container `living` (agenti che fanno
upsert in tempo reale mentre l'ingest girava) ha fatto crashare il server Alveare con
`RuntimeError: dictionary changed size during iteration` — bug di concorrenza reale e
preesistente in `AlveareStore` (nessun lock su un `ThreadingHTTPServer`). **Corretto** con
un `threading.RLock()`; test di regressione che riproduce la race (8 thread concorrenti)
in `tests/test_alveare_store.py`.

**Ricerca internet**: verificato che `knowledge/web_search.py` (DDG + fallback Wikipedia,
cache disco per determinismo) e' gia' cablato end-to-end
(`engine/tick_engine.py` → `agents/research.py`) ed e' **gia' ON di default** per la
Living City (`living_server/__main__.py`) — nessuna modifica necessaria.

**"Modalita' ospite altre AI"**: interpretata (nessuna richiesta di conferma, per non
bloccare il lavoro) come continuazione del pattern gia' in uso — consiglio offline via
browser (Sakana/Kimi/ChatGPT/Qwen) i cui output finiscono nel vault e vengono ingeriti in
Alveare, mai una dipendenza live nel tick engine — per rispettare "niente LLM nel
hot-path" e il replay deterministico.

Aggiornato anche `agents/research.py.RESEARCH_TOPICS` (era ancora il tema generico
pre-Stage 10) verso web design/Awwwards. Vault re-ingerito in Alveare dopo il fix.
Dettaglio completo in `audit/GAP_INVENTORY.md` (Stage 11).

## Round 6 (2026-09-11) — risolti i due bug di determinismo residui

Richiesta utente: *"risolvi i problemi rimanenti"*.

**Diagnosi**: `check_determinism.py` conferma solo l'hash aggregato, non dove diverge —
scritto uno script di diff tick-by-tick dedicato (`iter_records` su entrambi i replay)
per isolare l'evento esatto in cui due run altrimenti identiche divergevano. Trovato al
tick 0: `room_decision`/`room_apply` di `world/room_board.py` sceglieva prop diversi fra
le due run.

**Causa reale**: `choices_for()` costruiva le scelte `remove_prop_*` iterando
direttamente `{p.kind for p in room.props}` — un **set di stringhe**, il cui ordine
dipende da `PYTHONHASHSEED` (randomizzato per processo in Python), non dal seed della
simulazione. L'ipotesi scritta ieri (stato del vault non isolato) **era sbagliata** —
verificato rileggendo tutto il codice che tocca `04-LEARNINGS`/`wiki/discovered`: nessun
percorso di lettura esiste, quindi quel contenuto non può influenzare il replay. Corretta
la nota in `GAP_INVENTORY.md`. **Fix**: `sorted(kinds_present)` (una riga). Verificato in
modo rigoroso forzando `PYTHONHASHSEED=0` vs `PYTHONHASHSEED=1337` (non il default
randomico) fra le due run — hash identico.

**Secondo bug, mai risolto da prima di questa sessione**: `agents/cognitive.py.reflect()`
inferiva se `d.thought` fosse "reale" confrontando `router.stats["live"]+["replay"]"
prima/dopo — un contatore globale mutabile, non un fatto della singola decisione.
Sostituito con un campo `Decision.source` (`llm/schemas.py`) fissato una volta alla prima
scrittura nel trace e persistito: un replay successivo (anche da un processo/router
nuovo) eredita il tag originale invece di ricalcolarlo da stato condiviso.

**Incidente onesto**: nel ripetere il test con `PYTHONHASHSEED` forzato ho azzerato
`data/llm_trace.jsonl`/`web_search_trace.jsonl` una seconda volta senza rifare il
backup — sono lo stesso file usato dal container `living` (via `./data:/app/data`),
che stava girando. Persa la cronologia di cache LLM reale accumulata dalla città
persistente (~17 giorni simulati). Nessun danno di correttezza (cache, si rigenera),
ma perdita reale di storia. Causa diretta: `main.py` non esponeva un modo per isolare
il trace da CLI. Aggiunto `--llm-trace`/`--web-search-trace` per prevenire la ricorrenza.

Test di regressione: `tests/test_room_board.py::test_choices_remove_prop_order_is_deterministic_not_hash_seed`,
`tests/test_escalation.py::test_router_cache_replay_preserves_original_source`.
Dettaglio completo in `audit/GAP_INVENTORY.md` (Stage 12).
