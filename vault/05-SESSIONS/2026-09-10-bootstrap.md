---
tags: [autopolis, session, bootstrap]
date: 2026-09-10
---

# Session — vault bootstrap condiviso

## Obiettivo

Completare vault Obsidian condiviso per **tutti** gli agenti Autopolis e sync Aether + Alveare ingest.

## Deliverable

- Wiki: [[06-MEMORY/wiki/freellmapi]], [[06-MEMORY/wiki/self-learning-loop]], [[06-MEMORY/wiki/paperclip-city]]
- Collective: [[01-AGENTS/collective]]
- Prompt contract: [[07-PROMPTS/cognitive-json]]
- Script sync → `D:/AETHER-VAULT/04-PROJECTS/autopolis/`
- `docker-compose.yml`: volume Alveare `AETHER_VAULT_PATH:-./vault`

## Stack verificato

- FreeLLMAPI `:3001/v1` (profile `llm`)
- Alveare `:9200` ingest vault
- Movimento FSM: no LLM

## Next

- Run `simulator-llm` con vault ingested
- Append learnings runtime in [[04-LEARNINGS/lessons-learned]]
