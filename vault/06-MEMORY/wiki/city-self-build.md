---
tags: [civitas, city, growth, sakana]
updated: 2026-09-10
---

# Città che si autocostruisce

Gli AGI-OS **lavorano / studiano / si auto-migliorano**. Due motori in parallelo:

1. **Escrow agente** (`world/construction.py`) — come il reel Civitas (Accord/Cafe):
   un agente propone con soldi propri, altri contribuiscono, dopo N giorni nasce il POI.
2. **Metriche collettive** (`world/city_growth.py`) — soglie skill/job/lesson → blueprint.

```
AGI-OS decide build_choice (LLM raro)
   → propose (escrow) / contribute
   → ConstructionBoard.tick_day
   → city_build (source=agent_escrow) + register_poi
   → pull sociale verso il cantiere / AgentCafe
```

## Parità vs reel Instagram

| Reel | Noi |
|------|-----|
| Agente spende soldi per Cafe | `propose_cafe` + escrow `founder_min` |
| Altri costruiscono in giorni | `contribute` + `build_days` |
| Agenti si presentano | `record_visit` + suggest_social_poi |
| Deterministico / log | eventi `build_*` / `city_build` in replay |
| + | growth collettivo + Sakana blueprint + Living WS |

## Sakana + Playwright (infra design)

```powershell
python -m living_server --agents 12 --fast --hermes
python scripts/sakana_city_infra.py --living-url http://127.0.0.1:9300
```

## API

- `GET /v1/city` — pois + growth + **construction** (projects, escrow, visitors)

