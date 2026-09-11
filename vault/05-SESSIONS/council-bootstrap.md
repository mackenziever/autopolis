---
tags: [autopolis, session, council, freellm]
date: 2026-09-10
---

# Session — council bootstrap multi-modello

## Obiettivo

Consiglio architettonico **free-tier** per QA Autopolis: 5 seat via FreeLLMAPI + Sakana Playwright opzionale.

## Deliverable

- Catalog: `ops/council/models_catalog.yaml`
- CLI: `ops/council/run_council.py`
- Prompt: `ops/council/prompts/city_apparatus.md`
- Sakana wrapper: `scripts/council_sakana_playwright.py`
- Artefatti: `qa/council/latest.json`, `qa/council/latest.md`

## Stack

- FreeLLMAPI `:3001/v1` — POST `/chat/completions` parallelo per seat
- Env: `AUTOPOLIS_LLM_API_KEY`, `AUTOPOLIS_LLM_API_BASE`
- Override modello: `COUNCIL_MODEL_<SEAT>`

## Validazione apparato (domanda council)

Come misurare self-improve reale + FreeLLM live + vault Alveare senza LLM nel movimento FSM.

## Next

1. Impostare unified key + almeno un provider in dashboard FreeLLM
2. Rerun council → confrontare risposte seat in `qa/council/latest.md`
3. Append learnings in [[04-LEARNINGS/lessons-learned]]

## Collegamenti

- [[06-MEMORY/wiki/freellmapi]] · [[06-MEMORY/wiki/self-learning-loop]] · [[AGENTS]]
