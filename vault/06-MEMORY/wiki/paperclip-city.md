---
tags: [civitas, wiki, control-plane, orchestration]
updated: 2026-09-10
---

# Paperclip City — control plane locale per task agenti

Metafora operativa: un **Paperclip-style control plane** locale che traccia
*issue* cognitive per ogni agente della città — senza SaaS esterno.

## Issue types (= eventi sim)

| Issue | Label | Trigger | Skill |
|-------|-------|---------|-------|
| `reflect` | Daily reflection | REST, 1×/day | [[02-SKILLS/reflect-and-improve]] |
| `career` | Career choice | job eligible + tick | [[02-SKILLS/career-ladder]] |
| `study` | Study focus | library/course POI | [[02-SKILLS/study-mastery]] |
| `social` | Social stance | plaza interaction | [[02-SKILLS/plaza-social]] |

Ogni issue è **aperta** quando lo state machine emette l'evento, **chiusa**
quando il JSON decisione è validato e la lesson è in coda Alveare.

## Stati issue (locale)

```
open → retrieving → deciding → applied → closed
                      ↓ (budget/timeout)
                   fallback_det
```

- **open**: evento in coda cognitive worker
- **retrieving**: query Alveare + episodic memory
- **deciding**: FreeLLMAPI `:3001/v1` (fuori hot-path movimento)
- **applied**: runtime mutato (focus, job, course, stance)
- **closed**: lesson upserted, trace scritto

## Board condiviso vs silo privato

| Layer | Scope | Storage |
|-------|-------|---------|
| Issue board | per-agente, runtime | `AgentRuntime` + tick trace |
| Knowledge base | **tutti gli agenti** | vault + Alveare |
| Ops dashboard | umano | FreeLLM UI, metrics :9100 |

Gli agenti **condividono** le lezioni chiuse; le issue aperte restano private fino al merge in Alveare.

## Ops bridge

Tool fuori sim (non nel tick loop):

- `alveare-query` — ispeziona retrieval
- `alveare-ingest` — re-sync vault dopo edit umano

Vedi `ops/civitas_ops.py`.

## Anti-pattern

- ❌ LLM per pathfinding o collision response
- ❌ Issue `reflect` ogni tick (solo daily)
- ❌ Secret nel vault o nel trace

## Collegamenti

- [[AGENTS]] · [[01-AGENTS/collective]] · [[06-MEMORY/wiki/freellmapi]]
- [[06-MEMORY/wiki/self-learning-loop]]
