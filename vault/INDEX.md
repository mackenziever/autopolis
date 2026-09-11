---
tags: [civitas, vault, index, alveare]
updated: 2026-09-10
---

# Civitas Vault — Index (condiviso per tutti gli agenti)

Vault Obsidian-compatible: memoria collettiva di **tutti** gli agenti simulati + ops FreeLLM/Alveare.

## Gerarchia (Karpathy / Aether)

| Livello | Path | Uso |
|--------|------|-----|
| 1 Operativo | [[SOUL]] · [[AGENTS]] | identità, routing, ordini |
| 2 Skills | [[02-SKILLS/README]] | procedure riutilizzabili (reflect, career, study, social) |
| 3 Mondo | [[03-WORLD/README]] | POI, corsi, lavori, mappa |
| 4 Learnings | [[04-LEARNINGS/README]] | lezioni self-improve + ricerca |
| 5 Sessioni | `05-SESSIONS/` | rollup run |
| 6 Wiki | `06-MEMORY/wiki/` · `wiki/discovered/` | conoscenza profonda + scoperte AGI-OS |
| Catalogo | [[00-META/KNOWLEDGE-CATALOG]] | indice di tutto ciò che viene salvato |

Runtime vivente: ogni reflect/career/build/research scrive nel vault **e** upserta Alveare
così la conoscenza è accessibile a **tutti** gli agenti.

## Stack inferenza

- **FreeLLMAPI** → `http://127.0.0.1:3001/v1` (free tier aggregati)
- **Alveare RAG** → `http://127.0.0.1:9200` (ingest di questo vault)
- Movimento FSM: **senza LLM**. Cognizione: eventi rari + self-improve.

## Mirror Aether

Copia ufficiale anche in `D:/AETHER-VAULT/04-PROJECTS/civitas/`.
Ingest: `python scripts/alveare_ingest_vault.py --vault vault`

## Collegamenti

- [[SOUL]] · [[AGENTS]] · [[02-SKILLS/README]] · [[03-WORLD/README]] · [[04-LEARNINGS/README]]
- [[06-MEMORY/wiki/freellmapi]] · [[06-MEMORY/wiki/self-learning-loop]]
