---
tags: [civitas, prompts, json, contract]
updated: 2026-09-10
---

# Cognitive JSON — contratto decisione condiviso

Tutti gli eventi LLM in Civitas devono restituire **solo** JSON valido.
Parser: `llm.schemas.Decision.parse()` — scelta deve essere ∈ `choices` fornite.

## Schema

```json
{
  "choice": "<string from allowed choices>",
  "thought": "<rationale, max ~400 chars>",
  "confidence": 0.0
}
```

| Campo | Tipo | Regole |
|-------|------|--------|
| `choice` | string | **Obbligatorio.** Deve matchare esattamente una voce in `choices`. |
| `thought` | string | Obbligatorio logicamente; default `"Decisione senza commento."` se vuoto. Troncato a 400 char. |
| `confidence` | float | Opzionale, default `0.5`. Clamp `[0.0, 1.0]`. |

## System prompt (template)

```
Sei {display_name}, {age} anni. {biography}
Skill={skills}; lavoro={job}; corso={course_id}; focus={focus}; strategia={strategy}.
Scegli solo tra le opzioni date e restituisci JSON:
{"choice":"...","thought":"...","confidence":0.0}
```

Implementazione: `AgentCognitiveEngine.prompt()`.

## Context payload (non nel JSON output)

Il router riceve anche (non restituire nel JSON):

```json
{
  "memories": ["episodic hits..."],
  "alveare": [{"id","source","text","score","tags"}],
  "...event-specific fields"
}
```

## Esempi per evento

### daily_reflection

Choices: `consolidate_skills` | `recover_energy` | `seek_social` | `push_study`

```json
{"choice":"push_study","thought":"Energia alta, corso data half-done; conviene chiudere il modulo.","confidence":0.72}
```

### career_choice

Choices: subset di `eligible_jobs()` (es. `intern`, `clerk`, …)

### study_focus / social_stance

Choices fornite dal tick engine per POI/stanza corrente.

## Errori

| Errore | Comportamento |
|--------|---------------|
| JSON invalido | retry → fallback deterministico (hash seed) |
| `choice` ∉ allowed | `ValueError` → fallback |
| budget exceeded | skip LLM, fallback |

## Replay

Request/response registrati in `data/llm_trace.jsonl` con chunk Alveare completi.

## Collegamenti

- [[06-MEMORY/wiki/freellmapi]] · [[02-SKILLS/reflect-and-improve]]
- Codice: `llm/schemas.py`, `agents/cognitive.py`
