---
tags: [civitas, agents, routing]
updated: 2026-09-10
---

# Civitas — AGENTS (routing per tutti)

## Popolazione

Ogni `agent_NNN` ha Persona (frozen) + Runtime mutabile (`active_course`, job, skills, focus)
- [[01-AGENTS/agi-os-living]] · [[06-MEMORY/wiki/city-self-build]] — progresso → autocostruzione POI + Sakana blueprint.
**Questo vault è condiviso da tutti**: retrieval Alveare non è silos privato.

## Living City

Daemon: `python -m living_server` → http://127.0.0.1:9300 (panel + `/health` + `/v1/agents` + WS `/ws/city`).
Inferenza: FreeLLM `auto` (free-tier) + Hermes locale via `scripts/register_local_hermes_freellm.py`.

## Ruoli cognitivi (routing eventi → skill)

| Ruolo | Eventi | Skill |
|-------|--------|-------|
| **Reflector** | `daily_reflection` | [[02-SKILLS/reflect-and-improve]] |
| **Careerist** | `career_choice` | [[02-SKILLS/career-ladder]] |
| **Scholar** | `study_focus`, exam | [[02-SKILLS/study-mastery]] · [[02-SKILLS/exam-feedback]] |
| **Socializer** | `social_stance` | [[02-SKILLS/plaza-social]] |
| **Hive Keeper** | fine tick upsert | Alveare batch + [[04-LEARNINGS/README]] |

## Modelli FreeLLM

- Default: `auto` via FreeLLMAPI (fallback chain dashboard).
- Budget: `llm_daily_requests_per_agent` (≥4 eventi/giorno/agente).
- Offline / no key → fallback deterministico (sim continua).

## Tipi di persona (seed)

Vedi generatori in codice: metodica, socievole, prudente, ambiziosa, curiosa.
Tutti leggono le stesse skill del vault; la biografia filtra le scelte.

## Ops / Goose

- `alveare-query` / `alveare-ingest` — fuori hot-path
- Bootstrap: `scripts/bootstrap_freellm_stack.ps1`
