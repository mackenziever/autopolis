---
tags: [civitas, architecture, north-star]
updated: 2026-09-10
source: brief utente (Architettura Tecnologica e Design Pattern)
---

# Civitas — Architettura Tecnica (north star)

Simulazione cittadina di **50 agenti** con personalità, memoria, lavoro, economia escrow e governance democratica.
Obiettivo: **determinismo bit-perfect** + sostenibilità economica (LLM locale / free, non hot-path).

## 1. Framework cognitivi di riferimento

### Generative Agents (Park et al. / Stanford)
- **Memory Stream**: osservazioni timestampate in linguaggio naturale
- **Retrieval**: `Score = α·Recency + β·Importance + γ·Relevance` (cosine su embedding)
- **Reflection**: quando somma importance supera soglia → astrazioni di livello superiore
- **Hierarchical Planning**: piano giornata → ore → sotto-azioni 5–15 min

### Concordia (DeepMind)
- Entity-Component per tratti/memoria/catene di pensiero
- **Game Master**: arbitro LLM che valida intenzioni (escrow, regole) prima del commit di stato

### AI Town (a16z)
- Separazione netta: **loop simulazione HF deterministico** vs **inferenza LLM async LF**
- Latenza LLM non deve bloccare i tick

## 2. Runtime deterministico (Event Sourcing + Tick ECS)

1. Agenti/LLM → intenzioni async → **Input Queue** (ordine monotono + seed)
2. Tick engine consuma in sequenza → transizioni FSM/ECS
3. **Event Log immutabile** → replay bit-perfect

### Pattern obbligatori
- **Single-writer**: niente mutate dirette da thread LLM
- **Due frequenze**: Tick HF (movimento/collisioni) + Step LF (FSM, economia, diff stato)
- **PRNG seeded** per entità/sistema; iterazione ECS per Entity ID ordinato
- Payload LLM = evento schedulato a `T+n`, mai guida del tick corrente
- Niente wall-clock / rete non sincronizzata nel registro autorevole

## 3. Rendering / replay offline

- Sim logic ≠ renderer
- Fast-forward (es. 100×) poi cinematic da Event Log
- Web: Three.js / R3F — Offline: Unity / Godot / Unreal
- Interpolazione Hermite/B-spline; camera path da eventi economici/politici

## 4. Economia (ACE / escrow FSM)

Ciclo a somma controllata:
1. Blocco fondi committente → escrow immutabile
2. Condizioni strutturate (skill minima, celle mappa, pagamento progressivo)
3. Engine valida deliverable → sblocco crediti lavoratore

Istituto: formazione a crediti → upgrade skill → pricing lavoro dinamico.

## 5. Governance democratica

Proposta (reflection) → deliberazione sociale → voto YES/NO/ABSTAIN.
Fenomeni attesi (non bug): drift persona da interazione; divergenza reflection vs action.
Mitigazione: nello prompt di voto includere storico proposte dell’agente + CoT esplicito.

## 6. Stack LLM e sostenibilità

- **Zero-cost reactive**: movimento A*, bisogni, saldi = FSM/ECS
- **Event-driven cognitive**: conversazioni, planning orario, reflection, voto/proposta
- Locale preferito: vLLM/SGLang o llama.cpp; APC + continuous batching; FP8/AWQ
- Civitas attuale: FreeLLMAPI `:3001` + Alveare `:9200`; Hermes/Qwable/Qwythos solo se espliciti
- Hermes ops **fuori** hot-path (Goose recipes / squad)

### Ruoli modello (target paper)
| Modello | Ruolo |
|---------|--------|
| 7B/14B instruct | conversazioni veloci, JSON |
| 70B-class | reflection / planning / leggi |
| coder | validazione escrow / istituto |

## 7. Roadmap ingegneristica

1. Core event-sourced + hash stato identici a pari seed
2. Inferenza locale + prompt Planning/Reflection
3. Escrow FSM + istituto
4. Governance + anti-incoerenza nel voto
5. Export Event Log → pipeline cinematic

## Collegamenti repo

- Codice: `civitas_release/` (`START_HERE.md`, `README.md`)
- Vault cognitivi: `vault/SOUL.md`, `vault/AGENTS.md`
- Gap: `audit/GAP_INVENTORY.md`
