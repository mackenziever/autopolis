---
name: build-city
description: Proposta e finanziamento di edifici cittadini (escrow) da parte degli AGI-OS.
tags: [civitas, build, escrow, city]
---

# Skill — costruire la città

Puoi **proporre** un edificio spendendo i tuoi soldi in escrow, oppure **contribuire**
a un progetto aperto. Nessuno ti obbliga: è iniziativa civica.

## Opzioni tipiche

- `propose_cafe` — fondi un AgentCafe (serve founder_min in cassa)
- `propose_tower_lounge` — lounge su piano torre
- `propose_market_stall` — bancarella
- `contribute` — metti soldi su un progetto già aperto
- `skip_build` — non questa volta

## Regole

- Soldi tuoi → escrow → costruzione in N giorni di simulazione
- Altri agenti possono contribuire
- A costruzione finita nasce un POI reale sulla mappa
- Il movimento resta FSM/A* senza LLM
