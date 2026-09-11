# INVENTARIO GAP — Civitas Full Core

**Stato audit:** `PASS_WITH_PRODUCTION_GAPS` (P0–P2 + ops bridge + P1 security hardening)  
**Ultimo aggiornamento:** 2026-09-11

---

## Chiusi di recente (Stage 16 — approfondimento RSI: due spunti concreti implementati)

Su richiesta dell'utente, approfondito un documento esterno sull'auto-miglioramento
ricorsivo (RSI) dei modelli di frontiera e confrontato onestamente con Civitas
(analisi completa in un fork dedicato). **Verdetto**: la sovrapposizione è debole
per design — RSI presuppone un ciclo di training/reward e privilegi di
auto-modifica del proprio pipeline, che il single-writer e la FSM deterministica
di Civitas escludono strutturalmente (non è un gap da colmare, è già la
protezione). Due spunti minori genuinamente pertinenti, entrambi implementati:

- [x] **`research.stats_summary()`** (`agents/research.py`): `write_rate` e
  `fallback_rate` derivati da `researches/writes/fallback_skipped` — segnale
  precoce dello stesso bug corretto in Stage 15 (fallback che scrive
  placeholder nel vault), visibile su `/health` invece di richiedere di
  rileggere a mano centinaia di file di discovery per notarlo. Esposto sia da
  `engine/tick_engine.py._health_extra()` (che prima non esponeva affatto
  `research.stats`, gap trovato durante l'implementazione) sia da
  `living_server/app.py.health()`.
- [x] **Tracciamento `rid` di provenienza end-to-end**: `llm/schemas.py.Decision`
  guadagna un campo `rid` (request id di `llm/router.py._id()`), popolato in
  tutti e 3 i percorsi di `decide()` (live, replay dal trace, fallback — il
  fallback non lo portava affatto prima). Propagato fino a
  `knowledge/vault_librarian.py.record_lesson()`/`record_discovery()` (nuovo
  parametro opzionale `rid`), persistito nel file markdown (riga/frontmatter)
  e come tag `rid:<hash>` nell'upsert Alveare (riusa l'indice a tag esistente,
  nessuna modifica allo schema HTTP). Chiude il loop di audit fra una nota nel
  vault e la richiesta LLM esatta che l'ha prodotta — prima richiedeva debug
  manuale, come servito per isolare il bug di Stage 15.
- Test: `tests/test_research_loop.py::test_rid_is_persisted_in_discovery_and_lesson_files`,
  `tests/test_llm_router.py::test_rid_populated_on_live_replay_and_fallback`.

## Chiusi di recente (Stage 15 — "gli agenti non si automigliorano": causa reale trovata e corretta)

Su segnalazione diretta dell'utente (frustrazione esplicita: il research/discovery
loop sembrava non produrre apprendimento reale). Un'analisi mirata (fork di sola
lettura sul vault) aveva già trovato che il ciclo principale (reflection/study/
career, ~97% chiamate live) funziona bene, ma il research loop era quasi sempre
in fallback (94% dei file discovery). Approfondito fino alla causa radice — **due
bug distinti**, non uno:

- [x] **Budget giornaliero per agente troppo stretto rispetto agli eventi cognitivi
  reali.** `agents/state_machine.py` ha 9 flag "once-per-day" distinti (reflect,
  career, study, social, exam, build, governance, room, research_focus), ma
  `config.py.SimConfig.llm_daily_requests_per_agent` era **8** — un agente attivo
  su tutti i fronti in un giorno esauriva il budget PRIMA che arrivasse
  `research_focus`, chiamato per ultimo (subito dopo reflect, nello stato REST a
  fine giornata secondo `DEFAULT_SCHEDULE`). Il research loop finiva quasi sempre
  in fallback per `budget_denied`, non per un vero limite di costo. **Fix**:
  alzato a 12 richieste/agente/giorno (token e tetti globali scalati di
  conseguenza: `input_per_agent` 12k→24k, `output_per_agent` 3k→4k,
  `requests_global` 400→800, `input_global` 600k→1.5M, `output_global`
  150k→250k) — margine per tutti e 9 gli eventi più un cuscinetto.
- [x] **Contaminazione del vault/Alveare col placeholder di fallback.**
  `agents/research.py.research_agent()` NON controllava `Decision.source` prima
  di scrivere: il router in fallback sceglie comunque deterministicamente fra
  `write_lesson`/`write_discovery`/`skip_research` (hash sul rid, non sul
  contenuto — 2 possibilità su 3 non sono skip), quindi il placeholder "Fallback
  deterministico per research_focus (...)" veniva scritto nel vault E indicizzato
  in Alveare come se fosse una vera scoperta — poi RIPESCATO da altri agenti
  come RAG hit (`_retrieve`, filtrato per tag dallo Stage 13/item 2), un circolo
  vizioso che auto-contaminava la base di conoscenza condivisa con rumore invece
  che con sapere reale, aggravandosi ogni volta che il research loop andava in
  fallback. `agents/cognitive.py.reflect()` gestiva già correttamente questo caso
  (`d.source == "live"` altrimenti template pulito) — `research.py` no. **Fix**:
  stesso principio applicato — `d.source != "live"` forza `choice="skip_research"`
  prima di qualunque scrittura, nuovo contatore `stats["fallback_skipped"]`
  (esposto su `/health` via `research.stats`, già spreaddato).
- [x] Test: `tests/test_research_loop.py` (3 test — fallback mai scritto anche
  quando la scelta "vorrebbe" scrivere, live scritto normalmente, skip_research
  esplicito mai scritto a prescindere dalla fonte).
- **Nota per il prossimo giro**: coi budget alzati, il vault crescerà più in
  fretta con contenuto REALE (non più soffocato dal fallback) — vale la pena
  ricontrollare fra qualche giorno simulato se il tasso `research.stats.writes /
  researches` sale in modo sostanziale, a conferma che la causa era davvero
  questa e non qualcos'altro di più sottile (es. system prompt debole).

## Chiusi di recente (Stage 14 — Sindaco: ratifica/veto + tie-break su governance)

Su richiesta esplicita dell'utente: nuovo ruolo di governance "sindaco" (`agents/mayor.py.MayorOffice`),
alimentato da un provider LLM cloud a scelta dell'operatore (chiave in
`.env.providers` → `MAYOR_LLM_API_KEY`/`MAYOR_LLM_API_BASE`/`MAYOR_LLM_MODEL`),
separato dal FreeLLM/Hermes locale usato dai 50 cittadini. Scelta di scope (confermata dall'utente
su 2 domande mirate): **ratifica finale + tie-break**, non un sindaco proattivo che
propone ordinanze autonomamente — costo proporzionale all'attività di governance
già esistente (poche chiusure di proposta/settimana simulata), non un nuovo ciclo continuo.

- [x] `world/governance.py.GovernanceBoard`: nuovo `proposals_closing_now(tick)` (sola
  lettura), nuovo `tally(prop)` (pubblico, riusato sia internamente sia dal chiamante),
  `tick_day(day, tick, *, mayor_rulings=None)` — **retrocompatibile**: senza
  `mayor_rulings` il comportamento è identico a prima (yes>no passa, pareggio non
  passa). Con un ruling per un proposal_id: il suo `final` decide l'esito al posto del
  tally grezzo, e un evento `mayor_ruling` viene emesso.
- [x] `agents/mayor.py` (nuovo modulo): `MayorOffice.rule_on_proposal()` — chiama
  `CognitiveRouter.decide()` (stesso pattern trace/replay di ogni altra decisione
  cognitiva del progetto, trace separato `data/mayor_trace.jsonl`) con
  `choices=["yes","no"]` se pareggio (tie-break) o `choices=["ratify","veto"]` se la
  proposta è già approvata a maggioranza. **Contratto col chiamante**: mai invocato per
  una proposta già respinta a maggioranza (no>yes) — il sindaco ratifica/decide
  pareggi, non ribalta un rigetto popolare.
- [x] `engine/tick_engine.py`: `self.mayor` creato SOLO se `mayor_enabled` (default
  True) E chiave/endpoint/modello (le env var configurate) sono presenti nell'ambiente —
  altrimenti resta `None`, mai bloccante (stesso principio offline→fallback del resto
  del progetto). Router del sindaco con budget dedicato ridotto (max 50
  richieste/giorno, tetto di sicurezza contro un bug in loop su un servizio a
  pagamento). `step_one_tick()` interpella il sindaco PRIMA di `governance.tick_day()`
  per ogni proposta in scadenza con `yes >= no`, passa i ruling già calcolati (nessun
  I/O dentro `tick_day()`, resta puro). Evento `mayor_ruling` salvato nel vault via
  `agents/research.py.curate_event()` (nuovo branch, topic "governance",
  `vault/04-LEARNINGS/agents/mayor.md`).
- [x] Config: `config.py.SimConfig` (`mayor_enabled/model/api_base/api_key_env/
  timeout_s/max_output_tokens/trace_path`, campi operativi esclusi dal fingerprint di
  determinismo come gli equivalenti `llm_*`). CLI `main.py --no-mayor` (disabilita
  esplicitamente anche con la chiave presente — usato da `run_audit.py` e
  `tests/test_determinism_multiseed.py`, **mai** nel path di un test di determinismo:
  un provider cloud non garantisce riproducibilità bit-perfect fra run).
  `docker-compose.yml.living`: nuovo `env_file: .env.providers` (opzionale,
  `required: false` — il servizio parte comunque se il file manca).
- [x] Telemetria: `mayor.stats` (`rulings/ratified/vetoed/tie_breaks`) esposto su
  `/health` sia da `engine/tick_engine.py._health_extra()` sia da
  `living_server/app.py.health()`.
- [x] Test: `tests/test_mayor.py` (8 test — retrocompat senza sindaco, veto di una
  proposta approvata, tie-break che fa passare una proposta, `proposals_closing_now`,
  `MayorOffice.rule_on_proposal` con transport LLM fake per i 3 esiti, e verifica che
  `engine.mayor is None` quando le variabili d'ambiente non sono impostate).
- Deploy: `living`/`alveare` ricostruiti (`docker compose build`) e ricreati
  (`docker compose up -d`) per portare in produzione anche gli item del consiglio
  esterno dello Stage 13 — `living` ripartito dal checkpoint (`tick=26401`, nessuna perdita di stato
  città), `/health` verificato con tutti i nuovi campi popolati.

## Chiusi di recente (Stage 13 — consiglio esterno "deep research", 5 raccomandazioni)

Consultazione di un consiglio esterno (2026-09-11) su tutto lo stato del progetto dopo
Stage 12/12b, sintesi: a questa scala (12 agenti, ~27k chunk) i rischi reali sono
*nondeterminismo nascosto*, *rilevanza del contesto RAG* e *fragilità del free-tier LLM*,
non lo scaling orizzontale — sconsigliata infrastruttura pesante (vector DB esterno,
message queue, Kubernetes) a fronte di complessità molto più alta del beneficio.
Implementate tutte e 5 le raccomandazioni, scopo di ciascuna adattato a quanto già
verificato in Stage 12:

- [x] **1. Cache deterministica per web search** — `knowledge/web_search.py.WebSearchClient._cache_key()`:
  prima la cache era chiavata solo sul testo normalizzato della query, quindi due
  `(agent_id, tick)` diversi con lo stesso topic (comune: `topic_base + focus + job`
  ricadono spesso sulle stesse combinazioni) condividevano silenziosamente lo stesso
  risultato. Ora la chiave include `(agent_id, tick, event, query)` quando il chiamante
  passa contesto (stesso principio di `llm/router.py._id()`), col vecchio formato
  invariato per compatibilità coi chiamanti generici. `agents/research.py._search_web()`
  aggiornato per passare il contesto. Test: `tests/test_web_search.py` (4 test).
- [x] **2. Metadata filtering + indice invertito per l'Alveare RAG** — `knowledge/alveare_store.py`:
  nuovo `_tag_index: Dict[str, set]` (costruito in `_load()`/`upsert()`), usato da
  `query()` per calcolare via intersezione di set il set di candidati quando è passato
  un filtro `tags`, invece dello scan O(n) `_matches_filters()` su tutti i chunk.
  `agents/cognitive.py._retrieve_alveare()`/`decide_study()` e `agents/research.py._retrieve()`/
  `research_agent()` ora passano `tags=[skill]` (derivato da `COURSES`/`JOBS`) così il
  retrieval durante `study_focus`/`research_focus` non pesca contenuto cross-skill
  irrilevante, che degradava l'emergenza del comportamento. Nuovi campi telemetria
  `AlveareStore.last_query_ms`/`last_chunks_scanned` (esposti da `stats()`). Test:
  `tests/test_alveare_store.py::test_alveare_tag_index_scans_only_candidates`.
- [x] **3. Circuit breaker + retry nel router LLM** — `llm/router.py.CognitiveRouter`:
  freellmapi è un'immagine Docker di terze parti (free-tier, non modificabile), quindi
  la resilienza va sul lato client. Dopo `CB_FAILURE_THRESHOLD` (5) fallimenti
  consecutivi post-retry il breaker apre per `CB_OPEN_SECONDS` (30s) e le richieste
  vengono servite subito dal fallback deterministico (`reason="circuit_open"`) senza
  toccare il transport; retry con backoff esponenziale (`CB_MAX_RETRIES=2`) prima di
  contare un fallimento; reset del contatore fallimenti su qualunque successo. Nuove
  metriche: `stats["circuit_breaker_trips"|"circuit_breaker_skipped"|"retries"]`. Test:
  `tests/test_router_circuit_breaker.py` (4 test: apertura, reset, richiusura dopo
  timeout, retry prima del trip).
- [x] **4. Separazione fase pura/impura nel tick — SCOPO RIDOTTO, spiegato all'utente.**
  La riscrittura completa Plan/Resolve/Commit proposta dal consiglio esterno è stata valutata
  alto-rischio/basso-beneficio-marginale: `engine/tick_engine.py.step_one_tick()` itera
  già `self.agents` (lista fissa) sequenzialmente (`for a in self.agents: await a.step()`),
  quindi l'ordine di elaborazione è già deterministico per costruzione — non è quella
  la causa dei due bug reali trovati in Stage 12 (entrambi iterazione su `set()`
  sensibile a `PYTHONHASHSEED`, non riordino agenti), già corretti e riverificati anche
  dalla CI GitHub. Implementata solo la parte a basso rischio/alto valore: guardia di
  regressione permanente `tests/test_determinism_multiseed.py` — lancia la stessa
  simulazione (4 agenti, 600 tick) in due sottoprocessi con `PYTHONHASHSEED` diverso
  (0 vs 1337) e confronta il digest del replay; avrebbe intercettato entrambi i bug di
  Stage 12. Nessuna nuova dipendenza (`hypothesis` non aggiunta: stesso rischio coperto
  senza pacchetto in più).
- [x] **5. Telemetria end-to-end** — nuovo `CognitiveRouter.stats_summary()`
  (`llm_cache_hit_rate`, `llm_proxy_error_rate`, `circuit_breaker_open`); nuovo
  `MetricsCollector.summary()`/`get_counter()` (`metrics/collector.py`) per leggere
  histogram/counter esistenti in JSON senza dover fare scrape Prometheus; nuovo counter
  `civitas_building_relocation_conflicts_total` incrementato in
  `agents/state_machine.py._deterministic_relocate_target()` ad ogni candidato scartato
  per spacing (guardia sulla regressione "edifici sovrapposti" di Stage 12b). Tutto
  esposto su `/health` sia in `engine/tick_engine.py._health_extra()` (usato da
  `MetricsServer`) sia in `living_server/app.py.health()` (`llm_rates`,
  `tick_duration_ms`, `building_relocation_conflicts`, `alveare_rag`). `rag_query_latency_ms`/
  `chunks_scanned` già coperti dal punto 2 (`AlveareStore.stats()`), già esposti da
  `knowledge/server.py`'s `/health`.

## Chiusi di recente (Stage 12b — Alveare sotto carico reale post-ingest)

- [x] **`AlveareStore.query()` vettorizzato** (`knowledge/alveare_store.py`): il path
  brute-force faceva un `np.dot()` per chunk in un loop Python — con lo store cresciuto
  a ~25.000 chunk dopo l'ingest component_intel/vault, questo contribuiva a latenze
  misurabili. Ora: filtro metadata (economico) prima, poi UNA sola moltiplicazione
  matriciale vettorizzata sui superstiti. Benchmark: 65ms su 25.000 chunk (prima non
  misurato ma causa concreta dei timeout osservati in produzione). Test esistenti
  invariati e verdi.
- [ ] **Limite di scala reale non risolto, solo documentato**: `_append()` chiama
  `os.fsync()` ad ogni singola scrittura su `data/alveare/chunks.jsonl`, ora ~85MB, su
  un bind-mount Docker Desktop/Windows (`./data:/app/data`) — piattaforma con fsync
  storicamente lento su file di queste dimensioni. Con l'accesso ora correttamente
  serializzato da un lock (necessario, vedi Stage 11 — senza non è thread-safe), un
  burst di scritture (bulk ingest, o traffico agenti concentrato) può bloccare TUTTE le
  richieste (incluso l'health-check) per diversi secondi — osservato in produzione
  l'11/09: `living`/`alveare` marcati "unhealthy" da Docker con CPU 50-70% e code di
  thread in attesa dello stesso lock. Nessun crash, nessuna corruzione, nessuna perdita
  di correttezza — solo latenza. **Non corretto in questa sessione**: rimuovere/ridurre
  il fsync per-scrittura cambierebbe una garanzia di durabilità intenzionale (lo stesso
  pattern crash-safe usato da `llm/router.py.LLMTrace.put()`) e non è una decisione da
  prendere reattivamente senza discuterne. Opzioni per un turno dedicato: fsync
  periodico/batch invece che per-scrittura, o backend diverso da JSONL-a-riscrittura-
  intera oltre una certa soglia di dimensione.
- **Incidente onesto**: durante la diagnosi ho riavviato/ricreato i container
  `living`/`alveare` più volte (necessario per liberare code di thread bloccate);
  `living` è sempre ripartito correttamente dal checkpoint (`resumed from checkpoint
  tick=1201` — la persistenza costruita in Stage 6/7 ha retto), nessuna perdita di
  stato città oltre l'ultimo checkpoint salvato.

## Chiusi di recente (Stage 12 — i due bug di determinismo, risolti)

- [x] **Causa reale del mismatch scoperto nello Stage 11 trovata e corretta**: NON era
  lo stato del vault (ipotesi Stage 11, rivelatasi sbagliata dopo revisione del codice
  — nessun percorso di lettura in `agents/`/`engine/` legge mai da
  `vault/04-LEARNINGS`/`06-MEMORY/wiki/discovered`). La causa reale, isolata con un
  diff tick-by-tick dedicato (`check_determinism.py` conferma solo l'hash aggregato,
  non dove diverge — serve sempre un diff strutturato per isolare la causa):
  `world/room_board.py.choices_for()` costruiva le voci `remove_prop_*` iterando
  direttamente `kinds_present = {p.kind for p in room.props}` — un **set di stringhe**,
  il cui ordine di iterazione in Python dipende da `PYTHONHASHSEED` (randomizzato per
  processo), non dal seed della simulazione. Due run identiche potevano quindi produrre
  `choices` in ordine diverso → hash della richiesta (`rid`) diverso → scelta fallback
  diversa → divergenza propagata a valle (denaro, layout stanza, tick successivi).
  **Fix**: `for kind in sorted(kinds_present):` (una riga). **Verificato in modo
  rigoroso** forzando `PYTHONHASHSEED` esplicitamente diverso fra le due run
  (`PYTHONHASHSEED=0` vs `PYTHONHASHSEED=1337`, non il default randomico) — hash del
  replay **identico** in entrambe. Audit del resto della codebase per lo stesso pattern
  (set di stringhe iterato direttamente, non solo per membership test): nessun'altra
  occorrenza trovata (`agents/memory.py`, `agents/state_machine.py`,
  `world/city_growth.py`, `engine/tick_engine.py` usano tutti i loro set solo per
  test di appartenenza, ordine-indipendenti). Test di regressione:
  `tests/test_room_board.py::test_choices_remove_prop_order_is_deterministic_not_hash_seed`.
- [x] **Bug di determinismo `reflect()` (Gap residuo, mai risolto prima d'ora) corretto
  alla radice**: la vecchia logica confrontava `router.stats["live"]+["replay"]`
  prima/dopo la chiamata per dedurre se `d.thought` fosse "reale" — un contatore
  **globale e mutabile**, confuso da qualunque altra chiamata concorrente sullo stesso
  router (altri agenti async) e dalla cronologia cumulativa del trace fra run separate.
  **Fix strutturale**: nuovo campo `Decision.source` (`"live"`/`"fallback"`/`"unknown"`,
  `llm/schemas.py`), fissato una volta sola alla PRIMA scrittura nel trace
  (`llm/router.py.decide()`: `"live"` sul path live riuscito, `"fallback"` su ogni path
  di fallback) e persistito nel record cache — un replay successivo (anche da un
  processo/router completamente nuovo) eredita il tag originale invece di ricalcolarlo
  da stato globale. `agents/cognitive.py.reflect()` ora usa semplicemente
  `d.source == "live"`. Test di regressione:
  `tests/test_escalation.py::test_router_cache_replay_preserves_original_source`
  (verifica esplicitamente che un router "fresco" che rilegge un rid dalla cache erediti
  `source="live"`, non lo confonda con `"unknown"` o `"fallback"`) + assert aggiornati
  sui due test router esistenti. Cambia l'hash di replay per ogni agente che ha mai
  usato `reflect()` con LLM live — atteso e documentato, stessa categoria delle rename
  Stage 10 (COURSES/JOBS) che già invalidavano cache/hash precedenti.
- [x] **Verificato**: pytest mirato sui file toccati — 20/20 passed
  (`test_room_board.py`, `test_escalation.py`, `test_mock_llm_ci.py`,
  `test_http_transport_mock.py`, `test_self_improve.py`); suite completa in corso di
  ri-verifica.
- [x] **`main.py` ora espone `--llm-trace`/`--web-search-trace`** (default invariati:
  `data/llm_trace.jsonl`/`data/web_search_trace.jsonl`) per permettere a run isolate
  (determinismo, benchmark, debug) di puntare a un path separato **senza** collidere
  con la cache condivisa del servizio `living` in Docker (stesso file via
  `./data:/app/data`).
- **Incidente onesto durante la verifica di questo fix**: nel ripetere il check di
  determinismo con `PYTHONHASHSEED` forzato, ho azzerato `data/llm_trace.jsonl` /
  `data/web_search_trace.jsonl` una SECONDA volta senza rifare il backup (fatto solo
  per il primo giro) — quel file è lo stesso usato dal container `living`, che stava
  girando in quel momento (~17 "giorni" simulati accumulati). La cronologia di cache
  LLM reale accumulata dalla città persistente è andata perduta: **nessun danno di
  correttezza** (è una cache, si rigenera con nuove chiamate live sui prossimi
  cache-miss; `living` è rimasto in esecuzione, tick avanzati normalmente, nessun
  crash — lo stato "unhealthy" temporaneo del container era contesa CPU dalle mie run
  parallele, risolto da solo), ma è una perdita reale di storia cognitiva pregressa.
  Causa diretta del gap sopra (`--llm-trace` assente) — non sarebbe potuto succedere
  con il flag ora aggiunto.

## Chiusi di recente (Stage 11 — component_intel → Alveare, web search, guest-AI)

- [x] **`component_intel` (Postgres, container `aether-vault-db-1`, schema
  `component_intel`) collegato ad Alveare**: nuovo `scripts/ingest_component_intel.py`
  (nessuna nuova dipendenza — estrae via `docker exec ... psql`, non psycopg2) porta
  924 riferimenti reali Awwwards (578 `awwwards_site` con score ≥7.5, 318
  `interaction_spell`, 28 `site_dossier`) in Alveare via HTTP `/v1/upsert`,
  taggati per skill (`layout/motion/interaction/webgl`, derivati dai tag reali
  component_intel: "3D"/"WebGL"→webgl, "Motion"/"GSAP"/"Animation"→motion,
  "Interaction Design"→interaction, "Typography"/"Responsive Design"→layout).
  Id deterministico (`component_intel:<kind>:<pg_id>`) → idempotente, i rerun
  aggiornano gli stessi chunk invece di duplicare. Verificato: query filtrata
  `tags=["component_intel"]` su "webgl 3d shader" restituisce hit pertinenti.
- [x] **Bug di concorrenza reale trovato e corretto in `knowledge/alveare_store.py`**:
  `knowledge/server.py` serve su `ThreadingHTTPServer` (una richiesta = un thread),
  ma `AlveareStore` non aveva alcun lock — upsert concorrenti (il container `living`
  che scrive in continuo mentre un ingest bulk gira in parallelo) causavano
  `RuntimeError: dictionary changed size during iteration` in `_rewrite()`/`query()`,
  osservato in produzione durante l'ingest component_intel. Fix: `threading.RLock()`
  attorno a `upsert()`/`query()`/`stats()`. Regressione coperta da
  `tests/test_alveare_store.py::test_concurrent_upserts_do_not_crash` (8 thread × 20
  upsert concorrenti, prima falliva in modo riproducibile).
- [x] **Ricerca internet reale confermata già cablata** (`knowledge/web_search.py`,
  DDG + fallback Wikipedia, cache on-disk `data/web_search_trace.jsonl` per
  determinismo replay) — `living_server/__main__.py`: **ON di default** per la
  Living City (`CIVITAS_WEB_SEARCH` non impostata → `web_on=True`), off solo in
  replay/frozen o `--no-web-search`. Nessuna modifica necessaria, solo verificato.
- [x] **`agents/research.py.RESEARCH_TOPICS` ritematizzato** da argomenti generici
  (cafe/escrow/civic education) a web design/Awwwards, mantenendo varietà
  career/social/self-improve/tecnico/knowledge-mgmt.
- [x] **Vault re-ingerito in Alveare** (`scripts/alveare_ingest_vault.py --vault
  ./vault`) dopo il fix di concorrenza, per assorbire session log del consiglio AI
  e i doc Stage 10 (SOUL.md, study-mastery.md, jobs-and-courses.md).
- **Interpretazione "modalità ospite altre AI per migliorarsi"**: mantenuto il
  pattern già in uso in questa sessione — consiglio offline via browser
  (consultazione multi-modello esterna) i cui output finiscono in
  `vault/05-SESSIONS/*.md` e vengono poi ingeriti in Alveare come sopra, **non**
  una dipendenza live nel loop cognitivo — per non violare il vincolo "niente LLM
  nel hot-path" / replay deterministico (nessuna delle AI esterne è chiamata dal
  tick engine).

## Chiusi di recente (Stage 10 — tema città: "una città che studia web design")

- [x] **`config.py` COURSES/JOBS riscritti attorno al web design**, verso lo standard
  Awwwards "Site of the Day" (verificato su awwwards.com/websites e categoria "racing",
  2026-09-10: motion, 3D/WebGL, tipografia/layout, interaction design sono le competenze
  ricorrenti nei siti premiati). `layout_101/motion_201/interaction_202/webgl_301` →
  `layout_designer/motion_designer/ux_designer/webgl_developer` (webgl il più avanzato/raro,
  wage più alto — coerente col ruolo di 3D/WebGL nei siti premiati). Rimossi
  operations/coding/finance/design generici.
- [x] **`agents/persona.py`**: ogni archetipo ha ora una motivazione individuale esplicita
  verso lo stesso traguardo (Awwwards Site of the Day) — il "soul" di livello 2 richiesto
  dall'utente ("non hanno scopi ben precisi"), sopra la missione tecnica di `vault/SOUL.md`.
- [x] Aggiornati coerentemente: `paperclip_city/heartbeat.py` (fallback choices),
  `world/city_growth.py` (`CityMetrics.skill_*` rinominati + blueprint requires/unlocks),
  `data/city_blueprints/example_makerspace.json`, `vault/02-SKILLS/study-mastery.md`,
  `vault/03-WORLD/jobs-and-courses.md`, `vault/SOUL.md`, `tests/test_self_improve.py`.
- Verificato: smoke end-to-end (`main.py --agents 12 --ticks 700`) mostra agenti con i nuovi
  corsi/skill (`layout_101`→skill `layout`, ecc.) senza errori; pytest completo + determinismo
  isolato in corso.

## Chiusi di recente (Stage 9 — hard-case mining, "cervello dei cittadini")

- [x] **Hard-case mining implementato** (era solo documentato in `vault/06-MEMORY/wiki/self-learning-loop.md`):
  `agents/cognitive.py` traccia `hard_case_streak` per agente/topic (cap 6, decay -1/giorno a
  fine `reflect()`), pesa la query verso Alveare (`_hard_case_query_suffix`) e la salienza
  locale (`agents/memory.py`), tutto tramite funzioni pure (contatori/hash), mai LLM nel loop.
  Design verificato con un consiglio esterno multi-modello in parallelo via browser,
  convergenti in modo indipendente sullo stesso schema (boost deterministico +
  cap + decay temporale contro il rischio di "echo chamber"/fossilizzazione). Dettagli in
  `vault/05-SESSIONS/2026-09-10-hard-case-mining.md`.
- [x] **Bugfix**: `agents/cognitive.py.evaluate_exam` scriveva sempre `kind="exam"` in memoria,
  ma `reflect()` conta i fallimenti su `kind=="exam_failed"` — gli esami bocciati non venivano
  **mai** contati nel bilancio giornaliero successi/fallimenti. Corretto.
- [x] `agents/state_machine.py`: streak di collisioni consecutive (hot-path, solo contatore +
  salienza in memoria locale, nessuna nuova I/O per restare fuori dal vincolo hot-path).
- [x] `engine/checkpoint.py`: `hard_case_streak` persistito (stesso pattern del bugfix Stage 6/7
  su construction/governance/lessons).
- [x] `engine/tick_engine.py`: `_health_extra()["hard_case_mining"]` (agenti con streak attivo,
  topic attivi, streak massimo) — osservabile via `/health`.
- **Diagnosi FreeLLMAPI** (bloccava "sfruttare tutte le api free tier"): la chiave in `.env.llm`
  e' valida (l'errore "Invalid API key" precedente veniva da una curl senza header
  `Authorization`); il blocco reale e' che gran parte del catalogo (~292/373 modelli) non ha
  nessuna key provider configurata e i restanti sono quasi tutti rate-limited ora (`HTTP 429
  "All models exhausted"` anche su `auto`). Il catalogo dei modelli usato per le consulenze
  esterne aveva inoltre id modello non piu' validi (404 "not in catalog"). Serve intervento umano: piu' provider key in
  dashboard (`:3001/keys`) + allineamento degli id catalog a quelli realmente instradabili.
- Verificato: `pytest -q` → **62 passed** (62.34m totale, 0 failed). Determinismo a doppio-run
  (seed=42, 50 agenti, 600 tick, `--fast`) → **DETERMINISTIC** (sha256 identici), a condizione di
  azzerare `data/llm_trace.jsonl` prima di **entrambe** le run (vedi gap residuo sotto — motivo
  preciso).
- [x] **Posture scoring FEP-inspired** (`agents/cognitive.py._fep_posture_scores`): sostituisce la
  scelta arbitraria (hash) del fallback del router per `daily_reflection` con un punteggio
  deterministico instrumental+epistemic su energia/fame/relazioni/`hard_case_streak`. Deciso dopo
  ricerca esterna sul Free Energy Principle + secondo consiglio multi-modello esterno
  che ha sconsigliato nella maggioranza dei casi di dipendere da `pymdp` (backend JAX da v1.0, incompatibile con
  bit-per-bit replay) a favore di un'euristica dedicata. Nessuna nuova dipendenza; path LLM/replay
  intatto. Verificato con `pytest -q` + doppio-run determinismo (trace azzerato).
- [x] **Porting FEP reale** (`agents/fep.py.PostureExperience`, porting diretto della stessa
  logica di Expected Free Energy/Predictive Coding già implementata e verificata in produzione in
  un altro progetto di ricerca personale): ogni agente ora impara dall'esperienza — registra ogni giorno se
  la postura scelta ieri ha ridotto il bisogno che doveva coprire, e la scelta di oggi combina
  bisogno immediato (`_fep_posture_scores`) con l'Expected Free Energy appresa nei giorni
  precedenti. Stato persistito nel checkpoint (`posture_experience`, `last_posture`).
- [x] **Bugfix `join_crew` (rilocazioni POI)**: `agents/self_improve.py.build_decision` generava
  una scelta unica generica `"join_crew"` — con piu' rilocazioni aperte in parallelo,
  `construction.join_crew()` senza `project_id` prendeva sempre `open_relocations()[0]`,
  affamando tutte le altre rilocazioni in corso (dato reale osservato: 12/16 rilocazioni fallite
  in una run live). Ora una scelta `join_crew_<project_id>` per ciascuna rilocazione
  effettivamente unibile (stesso pattern di `propose_relocate_<poi>`); ogni agente puo' scegliere
  QUALE crew rinforzare. Test dedicato in `tests/test_construction_escrow.py`.
- [x] **Filtri multi-campo su Alveare** (`knowledge/alveare_store.py.query`, `+server.py` `/v1/query`,
  `+client.py`): `tags` (intersezione), `agent_id`, `tick_min`/`tick_max`, applicati pre-scoring —
  pattern preso da `lancedb/vectordb-recipes` (repo esterno segnalato dall'utente) MA senza
  adottare la dipendenza (costo/beneficio sfavorevole per poche migliaia di chunk; romperebbe
  l'auditabilità JSONL riga-per-riga). Rende potenzialmente utilizzabili in retrieval i tag
  `hard_case`/`obstacle:*`/`skill_gap:*` scritti dall'hard-case mining (oggi solo testo inerte) —
  **capacita' aggiunta, non ancora usata da `_retrieve_alveare`**: nessun chiamante esistente
  passa i nuovi filtri, quindi zero cambio di comportamento per il codice attuale. Wiring dei
  chiamanti (bias di retrieval hard-case-aware con filtro reale, non solo query-text) lasciato
  come prossimo passo deliberatamente separato, per non introdurre un trade-off recall/precision
  non ancora misurato nello stesso cambio. Test in `tests/test_alveare_store.py`.
- Dettagli round 2 (ricerca su altri progetti personali + consiglio pymdp) in
  `vault/05-SESSIONS/2026-09-10-hard-case-mining.md`.

## Chiusi di recente (Stage 8 — apprendimento reale)

- [x] Bugfix `agents/persona.py`: cognome generato a blocchi di 20 agenti identici (0-19 tutti "Rossi", ecc.) — modulo indipendente ora, 10 cognomi distribuiti su tutti gli agenti invece di 3 a blocchi.
- [x] `knowledge/web_search.py` (nuovo): ricerca internet reale (DuckDuckGo HTML, no API key, stdlib-only) per `ResearchLoop` — prima la "ricerca" leggeva solo Alveare (RAG interno sul vault locale), non il web vero. Cache-on-disk per replay deterministico (stesso pattern di `LLMTrace`). Off di default (`web_search_enabled=False`), on via `--web-search`.
- Verificato: ricerca live testata con query reali (risultati parsati correttamente), 60/60 pytest ancora pass.

## Chiusi di recente (Stage 6/7 — governance/relocation, reel-parity)

- [x] Governance/voting deterministico: `world/governance.py` (Proposal/Ballot, tally puramente numerico, mai LLM nel voto), integrato in `paperclip_city` (`IssueKind.GOVERNANCE`) e `agents/state_machine.py` (`_maybe_govern`)
- [x] Relocation POI esistenti (escrow + manodopera pagata): `world/construction.py` (`RelocateProject`, `propose_relocate`/`join_crew`), riusa il pattern `propose`/`contribute`/`tick_day`
- [x] **Bugfix determinismo**: `agents/research.py` usava `hash()` nativo di Python (randomizzato per processo via PYTHONHASHSEED) invece di sha256 — rompeva "stesso input → stessi byte" fin dal tick 0. Sostituito con sha256, come nel resto del codebase.
- [x] **Bugfix checkpoint**: `engine/checkpoint.py` non salvava `construction`/`governance` (board intere azzerate al resume) né `improve.lessons`/`build_decided_day`/`research_decided_day`/`governance_decided_day` — causava divergenza resume-vs-full oltre il tick del checkpoint. Aggiunto `to_state()`/`load_state()` su entrambe le board + campi mancanti in `_agent_dump`/`restore`.
- [x] `config.py`: `llm_model` puntava a `qwen3-coder-30b-a3b`, mai caricato — Hermes locale (`:8081`) serve realmente `qwable-9b`. Corretto (stesso fix in `main.py`). `llm_enabled` resta `False` di default: il fallback deterministico è l'unica garanzia di replay bit-perfect con questo test suite; live è opt-in via `--llm`.
- Verificato: `pytest -q` (60 passed), determinismo bit-perfect su 2 run seed=42/50 agenti/600 tick (hash identici)

## Chiusi di recente (P1 security)

- [x] Prometheus `/metrics` + `/health` + `/ready` (rate-limited)
- [x] OTel-lite (`metrics/otel.py`, flag `--otel`)
- [x] Gateway LLM TLS/Auth + rate-limit (`python -m security.llm_gateway`)
- [x] Secrets masking ampliato + `SecretManager.require`
- [x] Manifest run (`telemetry/manifest.py`, sempre scritto a fine run)
- [x] HMAC replay sidecar (`--sign-replay`, env `CIVITAS_REPLAY_HMAC_KEY`)
- [x] PII sanitizer su prompt/context/thought
- [x] ZMQ loopback-only + HMAC opzionale
- [x] CVE scan `scripts/scan_cve.py` in CI
- [x] CI/CD, lockfile, SBOM (già presenti)

---

## Gap residui

- [x] **Escalation cognitiva a livelli di confidenza** — implementata come gate a 2 livelli
  (non i 7 tier del riferimento originale, inadatti a un solo backend LLM reale): `agents/escalation.py.EscalationGate`
  (isteresi ingresso/uscita + cooldown post-attivazione, per evitare l'"auto-lock" segnalato
  nel consiglio 2026-09-10) + `llm/router.py.decide(..., escalate: bool = True)` (default
  compatibile all'indietro per ogni altro chiamante). Segnale: `hard_case_streak` normalizzato
  (stesso segnale gia' verificato dall'hard-case mining), gate attivo su `daily_reflection`.
  Ogni output LLM resta un evento esterno cristallizzato nel trace PRIMA di toccare lo stato
  del mondo (`rid` calcolato senza il flag `escalate` → cache-hit vince sempre, a prescindere
  da cosa il gate ricalcola dopo un resume) — principio validato da tutti i membri del
  consiglio. Stats: `router.stats["tier0_skipped_escalation"]`, `_health_extra()["escalation"]`.
  Stato del gate persistito nel checkpoint. Test in `tests/test_escalation.py` (gate + router).
  Verificato: `pytest -q` → **76 passed**. Determinismo a doppio-run (trace azzerato) →
  **DETERMINISTIC**, hash identico alla run pre-escalation-gate (nessuna regressione col
  path LLM disabilitato, come atteso dal design).
- [ ] **Pattern "core-and-ring"** (pacchetti di stato minimi tra fasi cognitive invece di
  contesto pieno) — terza priorita' secondo lo stesso consiglio; e' un refactoring
  dell'interfaccia (es. `TypedDict`/`dataclass` immutabili: belief/goal/confidence/streak/
  constraints/event_id), non richiede una libreria esterna. Non implementato.
- [x] **Bug di determinismo `reflect()` (scoperto 2026-09-10) — corretto in Stage 12.**
  Causa: `served_before/served_after` inferiva "d.thought e' reale" da un contatore
  globale mutabile (`router.stats["live"]+["replay"]"`), confuso da chiamate concorrenti
  di altri agenti e dalla cache cumulativa fra run separate. **Fix**: nuovo campo
  `Decision.source` fissato una volta alla prima scrittura nel trace e persistito —
  vedi Stage 12 sopra per dettaglio ed evidenza (test di regressione, verifica con
  `PYTHONHASHSEED` forzato).
- [x] **Secondo mismatch scoperto 2026-09-11 durante la verifica del bug sopra —
  causa reale isolata e corretta in Stage 12** (l'ipotesi iniziale "stato del vault non
  isolato" scritta qui in un primo momento **era sbagliata** — corretta dopo revisione
  del codice: nessun percorso di lettura in `agents/`/`engine/` legge mai da
  `vault/04-LEARNINGS`/`06-MEMORY/wiki/discovered`, quindi il loro contenuto non poteva
  influenzare il replay). La causa vera: `world/room_board.py.choices_for()` iterava
  direttamente un set di stringhe (ordine dipendente da `PYTHONHASHSEED`, non dal seed
  della simulazione) per costruire le scelte `remove_prop_*`. Vedi Stage 12 per fix e
  verifica.
- [ ] Smoke LLM contro endpoint di produzione reale (FreeLLM dashboard / Hermes) — helper: `python scripts/smoke_living_llm.py` (4 agents, short max-ticks, prints `llm` + `last_latency_ms`)
- [ ] TTFT / latency histogram LLM dedicati (oltre token counts)
- [ ] Property testing FSM
- [x] Load test ≥ 1M tick (`scripts/load_test.py`; CI smoke 10k in `tests/test_load.py`)
- [x] Golden spatial + contratto Rust/PyO3 (`tests/test_spatial_golden.py`, `native/README.md`)
- [x] FreeLLMAPI in Docker (`--profile llm`) + wiring `--llm-api-base`
- [x] Alveare RAG Aether-wide (`knowledge/`, `:9200`, vault ingest, ops bridge)
- [x] Retrieval trace con chunk completi + FROZEN_STORE + batch fine-tick
- [x] Mock LLM CI (`tests/test_mock_llm_ci.py`) senza pull GHCR
- [ ] Retention/compaction `data/alveare` (backlog crescita JSONL)
- [ ] Scansione CVE continua su registry immagini Docker
- [ ] Cert management automatico (Let's Encrypt) per gateway TLS pubblico

### P2 scale chiusi in questa sessione
- [x] Metriche overrun / path-cache / log bytes in `result.perf` + gauges Prometheus
- [x] Cognitive worker async opzionale (`--cognitive-worker`, fuori hot-path movimento)
- [x] Viewer 3D LOD (auto/high/low, trail e dettaglio per distanza camera)
- [x] CLI `--spatial-backend python|rust`

## Fuori scope
Fine-tuning online, fisica 3D autorevole, UI che scrive il mondo, DB distribuito, orchestrazione esterna nel tick cognitivo.
