---
tags: [civitas, agents, collective, alveare]
updated: 2026-09-10
---

# Collective memory — tutti gli agenti condividono il vault

Civitas simula N agenti (`agent_001` … `agent_NNN`) con **persona frozen**
e runtime mutabile. La conoscenza procedurale è **una sola**: questo vault.

## Principio

> Un vault, un Alveare, molte biografie.

| Risorsa | Condivisa? | Path / store |
|---------|------------|--------------|
| SOUL, AGENTS, Skills, Wiki | ✅ sì | `vault/` |
| Learnings cross-agent | ✅ sì | `04-LEARNINGS/` → Alveare |
| Persona (nome, età, bio) | ❌ per-agente | seed + fingerprint |
| Episodic memory | ❌ per-agente | `EpisodicMemory` in RAM |
| Runtime (job, skills, focus) | ❌ per-agente | `AgentRuntime` |
| LLM trace / replay | per-run | `data/llm_trace.jsonl` |

## Retrieval condiviso

`AgentCognitiveEngine._retrieve_alveare` interroga lo **stesso** indice Alveare
per ogni agente. Le lesson di `agent_042` possono informare `agent_017` al prossimo
evento `study_focus` — filtrate da score semantico, non da ACL per-agente.

## Scrittura condivisa

A fine tick (Hive Keeper): batch upsert lesson sanitizzate da tutti gli agenti.
Tag tipici: `decision`, `self_improve`, `posture`, `career`, `study`, `social`.

## Ruoli cognitivi (stesso vault, prompt diversi)

Vedi [[AGENTS]] — Reflector, Careerist, Scholar, Socializer leggono le **stesse**
skill in `02-SKILLS/`; il system prompt include biografia e stato runtime locale.

## Mirror Aether

Copia canonica: `D:/AETHER-VAULT/04-PROJECTS/civitas/`
Sync: `scripts/sync_vault_to_aether.ps1`

## Collegamenti

- [[SOUL]] · [[06-MEMORY/wiki/self-learning-loop]] · [[06-MEMORY/wiki/paperclip-city]]
- [[05-SESSIONS/2026-09-10-bootstrap]]
