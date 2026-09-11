---
name: career-ladder
description: Scelta lavoro quotidiana tra ruoli per cui l'agente ha skill e slot liberi.
tags: [civitas, skill, career]
---

# Skill: Career Ladder

## Quando
Stato `WORKING` al POI Office, una volta/giorno.

## Vincoli
- Solo ruoli in `choices` (già filtrati per skill).
- `train_more` = resta e studia invece di cambiare.
- Non inventare job fuori lista.

## Procedura
1. Confronta wage implicito vs crescita skill.
2. Se skill mancanti → preferisci restare / train.
3. Se hai skill avanzate e slot → sali di grado.

## Output JSON
`{"choice":"<job|train_more>","thought":"...","confidence":0.0-1.0}`
