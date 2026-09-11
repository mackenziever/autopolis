---
tags: [civitas, wiki, freellmapi, inference]
updated: 2026-09-10
---

# FreeLLMAPI — gateway free-tier primario

FreeLLMAPI è il **unico ingresso LLM** per Civitas in produzione locale.
Aggrega provider free-tier (OpenRouter, Groq, ecc.) dietro un endpoint OpenAI-compatible.

## Endpoint

| Servizio | URL | Ruolo |
|----------|-----|-------|
| **FreeLLMAPI** | `http://127.0.0.1:3001/v1` | chat/completions, routing `openai/auto` |
| **Alveare RAG** | `http://127.0.0.1:9200` | ingest vault, query condivise |
| Simulator metrics | `http://127.0.0.1:9100/health` | tick engine (no LLM) |

## Contratto d'uso

1. **Bind locale**: `HOST_BIND=127.0.0.1` — mai esporre :3001 su LAN.
2. **Modello default**: `openai/auto` (fallback chain configurata nella dashboard FreeLLM).
3. **Key unificata**: `CIVITAS_LLM_API_KEY` dalla dashboard Keys → provider free-tier.
4. **Budget**: `llm_daily_requests_per_agent` — minimo 4 eventi/giorno/agente (reflect, career, study, social).

## Fuori dal hot-path movimento

Il tick engine FSM **non** chiama FreeLLMAPI. Solo eventi cognitivi rari:

- `daily_reflection` → reflect
- `career_choice` → career
- `study_focus` / exam → study
- `social_stance` → social

Movimento, collisioni, pathfinding: **deterministico, zero token**.

## Bootstrap

```powershell
.\scripts\bootstrap_freellm_stack.ps1
# oppure
docker compose --profile llm up -d
```

Dopo avvio: dashboard `http://127.0.0.1:3001` → aggiungi provider → copia unified key.

## Docker wiring

- `simulator-llm` → `CIVITAS_LLM_API_BASE=http://freellmapi:3001/v1`
- `alveare` → embed opzionale via stesso base URL; vault montato read-only

## Fallback offline

Senza key o provider down: `CognitiveRouter` usa fallback deterministico (hash seed + choices).
La simulazione **continua**; trace registra assenza risposta LLM.

## Collegamenti

- [[SOUL]] · [[06-MEMORY/wiki/self-learning-loop]] · [[07-PROMPTS/cognitive-json]]
- Skill: [[02-SKILLS/reflect-and-improve]] · [[02-SKILLS/career-ladder]]
