---
name: reflect-and-improve
description: Riflessione giornaliera e aggiornamento strategia/focus per qualsiasi agente Civitas.
tags: [civitas, skill, reflect]
---

# Skill: Reflect & Improve

## Quando
Stato `REST`, una volta al giorno (`reflected_day`).

## Input
- Successi (skill_unlock) e ostacoli (collision/exam) recenti
- Chunk Alveare su query reflection
- Skill/lavoro/corso correnti

## Procedura
1. Sintetizza la giornata in 1–2 frasi oneste.
2. Scegli **una** postura: `consolidate_skills` | `recover_energy` | `seek_social` | `push_study`.
3. Motiva la scelta con energia, soldi, skills e lezioni passate.
4. Scrivi una **lesson** riusabile per gli altri agenti.

## Output JSON
`{"choice":"<postura>","thought":"<strategia>","confidence":0.0-1.0}`

## Effetto runtime
`SelfImprovementLoop.apply_posture` → focus + micro-boost studio se focus=study + upsert Alveare.
