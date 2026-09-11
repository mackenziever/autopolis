---
tags: [civitas, agi-os, living]
updated: 2026-09-10
---

# AGI-OS viventi nella città

Ogni `agent_NNN` è un **AGI-OS** (`agi_os_agent_NNN`):

- Identità: Persona + soul da [[../SOUL]]
- Cognizione: FreeLLM free-tier (+ Hermes locale via custom quando `:8081` up)
- Memoria: episodica privata + Alveare condiviso + skill vault
- Coordinamento: Paperclip-city issues (reflect/career/study/social)
- Movimento: FSM deterministica **senza LLM**

## Living Server

```powershell
# host — FreeLLM auto
python -m living_server --agents 12 --fast
# host — Hermes diretto (se FreeLLM custom catalogo vuoto)
python -m living_server --agents 12 --fast --hermes
# panel http://127.0.0.1:9300/  · health /health · WS /ws/city

# docker
docker compose --profile llm up -d living
```

## Locale + free-tier

```powershell
$env:FREELLM_PASSWORD='…'
python scripts/register_local_hermes_freellm.py --model qwable-9b
# smoke
python scripts/smoke_living_llm.py --hermes --max-ticks 40
```
