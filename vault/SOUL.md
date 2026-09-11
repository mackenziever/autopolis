---
tags: [civitas, soul, identity]
updated: 2026-09-10
---

# Civitas — SOUL (Livello 1)

## Missione

Simulazione urbana deterministica con apparato cognitivo **reale**:
agenti che lavorano, studiano, socializzano e **si auto-migliorano** tramite
FreeLLMAPI (free tier) + Alveare (memoria condivisa) + questo vault.

**Civitas è una città che studia web design.** Lo scopo condiviso di ogni
cittadino (il "perché" studia, non solo il "cosa") è raggiungere lo standard
Awwwards Site of the Day: motion design, 3D/WebGL, tipografia/layout,
interaction design — le competenze che distinguono i siti premiati (vedi
`vault/02-SKILLS/study-mastery.md`, `config.py.COURSES/JOBS`). Ogni persona
(`agents/persona.py`) ha una propria motivazione individuale verso questo
stesso traguardo, coerente col proprio archetipo — questo è il "soul" di
livello 2, sopra la missione tecnica di livello 1 qui sotto.

## Ordini permanenti

1. **Priorità locale / free**: FreeLLMAPI (`:3001`) aggrega free tier; Hermes/Ollama solo se espliciti.
2. **Niente LLM nel hot-path movimento** — solo reflect / career / study / social.
3. **Replay deterministico**: chunk Alveare completi in trace; store frozen in `CIVITAS_REPLAY=1`.
4. **Vault-first**: ogni lezione utile → `04-LEARNINGS/` + upsert Alveare fine-tick.
5. **Sicurezza**: FreeLLM bind `127.0.0.1`; no secret in git.

## Apparato cognitivo

| Evento | Skill vault | Effetto |
|--------|-------------|---------|
| `daily_reflection` | [[02-SKILLS/reflect-and-improve]] | postura + focus + lesson |
| `career_choice` | [[02-SKILLS/career-ladder]] | job se idoneo |
| `study_focus` | [[02-SKILLS/study-mastery]] | `active_course` |
| `social_stance` | [[02-SKILLS/plaza-social]] | stance sociale |
| exam / skill unlock | [[02-SKILLS/exam-feedback]] | skills + hire |

Pattern ispirato a *Self-Learning-Agents*: feedback sugli esiti → lesson → retrieval successivo (no retrain pesi).

## Collegamenti

- [[AGENTS]] · [[INDEX]] · [[06-MEMORY/wiki/self-learning-loop]]
