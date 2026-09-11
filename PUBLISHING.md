# Civitas — verso la pubblicazione

Questo documento raccoglie: l'obiettivo dichiarato in questa fase, le
modalità d'uso previste dalla licenza, una spiegazione dettagliata della
struttura del progetto modulo per modulo, e una checklist concreta di cosa
resta da fare prima e dopo aver reso il repository pubblico su GitHub.

## Obiettivo

Il repository attuale (`github.com/mackenziever/civitas`) è privato. Gli
obiettivi discussi per la pubblicazione sono:

1. **Dimostrare, non solo dichiarare** un'architettura multi-agente
   deterministica e replay-perfetta — la sua proprietà distintiva (stesso
   seed → stesso hash di replay, byte per byte) è verificabile da chiunque
   clona il repo ed esegue `check_determinism.py`, non un'affermazione da
   prendere sulla fiducia.
2. **Comunicare che l'architettura è riusabile oltre le città** (vedi
   `README.md`, sezione "Oltre la città"): simulazioni economiche, formazione
   aziendale, ricerca in scienze sociali computazionali, NPC di gioco,
   logistica — il nucleo (FSM deterministica per la routine + LLM solo su
   decisioni rare + RAG condiviso + record/replay) non è specifico al dominio
   "città".
3. **Mantenere aperta la valorizzazione commerciale futura** — da cui la
   scelta di una licenza source-available (Apache 2.0 + Commons Clause)
   invece di una licenza open source permissiva pura: chiunque può leggere,
   studiare, forkare e usare il codice, ma non venderlo o offrirlo come
   servizio a pagamento senza una licenza commerciale separata dall'autore.
4. **Dare credito** alla fonte di ispirazione visiva del viewer 3D
   ([@massive.manas.exe](https://www.instagram.com/massive.manas.exe/), un
   remake 3D indipendente dello stesso concept Civitas).

Se uno di questi punti non riflette più l'intenzione reale, va corretto qui
prima di pubblicare — questo file è la fonte di verità sull'intento, non solo
un elenco di task.

## Modalità d'uso previste (licenza)

Apache License 2.0 + [Commons Clause](https://commonsclause.com/), testo
completo in [`LICENSE`](LICENSE). In pratica, per chi trova il repo su
GitHub:

| Chi | Cosa può fare |
|---|---|
| Chiunque | Leggere, clonare, studiare il codice liberamente |
| Ricercatori / studenti / hobbisti | Modificare, forkare, usare per progetti personali o di ricerca, anche pubblicandone a loro volta il codice (con attribuzione) |
| Aziende / team interni | Usarlo internamente (es. come base per un proprio simulatore) senza rivenderlo né offrirlo come servizio a terzi |
| Chiunque voglia venderlo o offrirlo come prodotto/servizio a pagamento | Deve richiedere una licenza commerciale separata all'autore — non è concesso dalla licenza di default |
| Contributor esterni (PR) | Da decidere esplicitamente: se accetti PR, ogni contributo rientra nella stessa licenza salvo accordo diverso (Apache 2.0 §5) — se non vuoi gestire contributi esterni per ora, dillo chiaramente in un `CONTRIBUTING.md` ("repo pubblico ma non accetta PR") |

## Struttura del progetto, in dettaglio

Il README ha un albero sommario; qui la responsabilità di ogni modulo e come
comunicano fra loro.

### Il tick, dall'alto in basso

`engine/tick_engine.py.CivitasEngine.step_one_tick()` è l'unico punto che
avanza lo stato del mondo di un tick. Per ogni agente, in ordine fisso (lista
`self.agents`, mai riordinata a runtime — è la base del determinismo):
chiama `AgentFSM.step()` (`agents/state_machine.py`), che decide il prossimo
stato/posizione con pura logica FSM. Solo quando l'agente incontra un evento
raro (fine giornata, arrivo a un traguardo di studio, ecc.) la FSM chiama
`agents/cognitive.py.AgentCognitiveEngine`, che a sua volta invoca
`llm/router.py.CognitiveRouter.decide()` — l'**unico** punto del codice che
può fare una vera chiamata di rete verso un LLM.

### Il router LLM: cache, budget, fallback

`llm/router.py` calcola un id deterministico dalla richiesta
(`agent_id + tick + event + choices + system_prompt + context`, hashato) e
lo cerca in `llm_trace.jsonl` (`LLMTrace`). Se lo trova, rilegge la stessa
risposta byte per byte (mai una seconda chiamata di rete per lo stesso
input). Se non lo trova, verifica il budget (`llm/budget.py.TokenBudget`,
richieste/token per agente e globali, per giorno) e il circuit breaker interno
(apre dopo N fallimenti consecutivi, serve fallback per un intervallo). Solo
se tutto è concesso tenta la vera chiamata; qualunque esito (successo,
fallimento, budget negato, offline) produce una `llm/schemas.py.Decision` con
un campo `source` ("live"/"fallback"/"unknown") e un `rid` (l'id di cui
sopra) — entrambi persistiti, per poter sempre distinguere "l'agente ha
davvero pensato" da "ha usato un fallback deterministico".

### La memoria condivisa (Alveare / RAG)

`knowledge/alveare_store.py.AlveareStore` è un piccolo motore RAG: chunk di
testo con embedding, un indice invertito a tag per filtrare velocemente per
skill/argomento, un thread separato che scrive su disco in batch (write-behind,
non blocca le letture). `knowledge/vault_librarian.py.VaultLibrarian` scrive
qui (e in file Markdown sotto `vault/`) ogni volta che un agente impara
qualcosa (`agents/research.py`) o riflette (`agents/cognitive.py.reflect()`);
altri agenti la interrogano per contesto prima di decidere. È la parte che
rende il comportamento collettivo emergente invece che indipendente
agente-per-agente.

### Il mondo fisico

`world/map.py.CityMap` è la griglia (più un anello di "wilderness" esplorabile
fuori dai confini cittadini). `world/construction.py` gestisce la costruzione
collettiva di nuovi edifici (escrow di fondi tra agenti), `world/governance.py`
le proposte/voti cittadini, `world/economy.py` il mercato del lavoro. Nessuno
di questi moduli chiama mai un LLM direttamente — ricevono solo l'esito già
deciso dalla FSM/cognitive layer.

### Il sindaco (governance con provider LLM separato)

`agents/mayor.py.MayorOffice` è l'unico "agente" che non è un cittadino: si
attiva solo quando una proposta di `world/governance.py` si chiude, per
ratificarla/vetarla o decidere un pareggio. Usa un `CognitiveRouter`
**separato** da quello dei cittadini (provider LLM a scelta dell'operatore
via `MAYOR_LLM_API_KEY`/`MAYOR_LLM_API_BASE`/`MAYOR_LLM_MODEL`, opzionale) —
se mancano, il ruolo semplicemente non esiste, nessun impatto sul resto
della simulazione.

### Persistenza e replay

`telemetry/logger.py` scrive un registro binario append-only (MessagePack)
di ogni evento di ogni tick — è il "master tape" da cui il viewer 2D
(`viewer/replay_viewer.html`) e `check_determinism.py`/`inspect_replay.py`
leggono. `engine/checkpoint.py` salva/ripristina lo stato completo a confini
di giorno, con un fingerprint di configurazione che rifiuta un resume
incompatibile invece di corromperlo silenziosamente.

### La città "viva" e il viewer 3D

`living_server/` è un processo a parte (Starlette/uvicorn) che tiene una
simulazione in esecuzione indefinita, con checkpoint automatico, ed espone
`/health`, `/v1/city`, `/ws/city` (WebSocket con gli snapshot) e `/live`
(il viewer 3D). Il viewer (`viewer/living_city_live.html` +
`viewer/city_kit.js`, Three.js) è puro consumatore: non scrive mai nello
stato del mondo, solo legge gli snapshot e li disegna.

## Checklist prima di rendere pubblico il repository

- [x] Verificata la storia git completa: nessuna chiave API reale è mai
  stata committata (`.env.*` sempre esclusi da `.gitignore`).
- [x] Rimossa l'unica email personale hardcoded trovata (`scripts/*.py`).
- [x] `LICENSE` + sezione Licenza in `README.md`.
- [x] Genericizzati i riferimenti a un altro progetto privato dell'utente
  (nome in codice e repo GitHub non più citati) in tutti gli 11 file
  tracciati che li contenevano — codice sorgente (`agents/fep.py`,
  `agents/escalation.py`, `agents/cognitive.py`, `tests/test_fep.py`) e
  documentazione interna (`ops/`, `audit/`, `vault/`). Il concetto tecnico
  citato (Free Energy Principle / Active Inference, routing multi-tier con
  circuit breaker) resta descritto, solo senza nome/path dell'altro repo.
- [ ] **Priorità bassa** — path assoluti Windows con il tuo username
  (`C:\Users\yuric\...`) sparsi in `ops/`, `vault/00-META/`,
  `.cursor/skills/`, alcuni `scripts/*.py` di automazione locale. Rivelano
  solo lo username, non una credenziale — pulizia cosmetica, da fare con
  find-and-replace mirato se vuoi un repo più anonimo.
- [ ] Rivedere `vault/` e `data/` prima del push finale: contengono ore di
  testo generato dagli agenti (riflessioni, conversazioni, lezioni) durante
  le sessioni di sviluppo — non contengono segreti, ma potrebbero contenere
  frasi generate da un LLM che non vuoi mostrare così come sono. Non ancora
  passato in rassegna riga per riga in questo giro.
- [ ] Decidere se il repo pubblico accetta Issues/Pull Request (GitHub
  Settings) — se sì, aggiungere un `CONTRIBUTING.md`; se no, dirlo
  esplicitamente nel README per evitare PR inattese.
- [ ] Cambiare la visibilità del repo (GitHub → Settings → Danger Zone →
  Change visibility → Public). Reversibile (puoi tornare privato), ma da
  fare consapevolmente: da quel momento tutta la storia dei commit — non
  solo l'ultimo stato — diventa visibile a chiunque.

## Checklist dopo la pubblicazione

- [ ] Aggiungere un badge di stato CI al README, se il workflow GitHub
  Actions resta verde (`.github/workflows/`).
- [ ] Considerare un primo tag di versione (es. `v0.1.0`) per dare un punto
  di riferimento stabile a chi clona il repo.
- [ ] Se accetti contributi esterni, monitorare Issues/PR con una cadenza
  dichiarata (anche "quando ho tempo" è meglio di silenzio indefinito).
