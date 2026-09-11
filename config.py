"""Configurazione centrale e deterministica di Civitas.

Ogni parametro che influenza il mondo vive qui. La tripla che determina
completamente un replay e': (versione del codice, questo config, seed) +
le decisioni esterne registrate (LLM) se abilitate.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, Tuple, List
import json

Coord = Tuple[int, int]

# ---------------------------------------------------------------------------
# Punti di interesse (POI). Coordinate in celle-griglia (x, y).
# ---------------------------------------------------------------------------
POIS: Dict[str, Coord] = {
    "Home":       (6, 6),
    "Office":     (54, 10),
    "Aula_101":   (10, 52),
    "Aula_202":   (20, 54),
    "Cafe":       (48, 50),
    "Gym":        (54, 40),
    "Plaza":      (32, 32),
    "Market":     (30, 8),
}

# Routine di base condivisa; le persone possono deviare (vedi persona.py).
# (tick_start, stato)
DEFAULT_SCHEDULE: List[Tuple[int, str]] = [
    (0,   "COMMUTING"),
    (70,  "WORKING"),
    (200, "EATING"),
    (230, "WORKING"),
    (330, "ATTENDING_CLASS"),
    (420, "EXPLORING"),   # fuori città / wilderness
    (470, "SOCIALIZING"),
    (530, "COMMUTING"),
    (560, "REST"),
]

# Landmark oltre il bordo città (celle; margin in SimConfig.wilderness_margin)
# Agenti EXPLORING camminano verso questi punti e tornano.
WILDERNESS_LANDMARKS: Dict[str, Coord] = {
    "Wild_North":  (32, -14),
    "Wild_South":  (32, 76),
    "Wild_East":   (76, 32),
    "Wild_West":   (-14, 32),
    "Wild_NE":     (70, -10),
    "Wild_SW":     (-10, 70),
}

# Corsi disponibili: course_id -> (POI, skill sbloccata, difficolta 0-100)
# Civitas e' una citta' che studia WEB DESIGN, con l'ambizione di raggiungere
# lo standard "Site of the Day" di Awwwards (awwwards.com): motion design,
# 3D/WebGL, tipografia/layout, interaction design — le competenze ricorrenti
# nei siti premiati (verificato su awwwards.com/websites e la categoria
# "racing", 2026-09-10). Difficolta' crescente rispecchia la rarita' reale
# di queste competenze: webgl e' la piu' avanzata/rara, layout la piu' base.
COURSES: Dict[str, Tuple[str, str, int]] = {
    "layout_101":      ("Aula_101", "layout",      35),
    "motion_201":      ("Aula_101", "motion",       45),
    "interaction_202": ("Aula_202", "interaction",  50),
    "webgl_301":       ("Aula_202", "webgl",        60),
}

# Mercato del lavoro: ruolo -> skill richiesta, stipendio/tick, posti
JOBS: Dict[str, Tuple[str, float, int]] = {
    "intern":          ("basic_literacy", 1.0, 999),
    "layout_designer": ("layout",         2.5, 15),
    "motion_designer": ("motion",         3.5, 10),
    "ux_designer":     ("interaction",    4.0, 8),
    "webgl_developer": ("webgl",          5.0, 6),
}


@dataclass
class SimConfig:
    # Popolazione e tempo
    num_agents: int = 50
    tick_rate_hz: int = 15
    total_ticks: int = 600
    day_length_ticks: int = 600          # 1 giorno simulato
    seed: int = 42

    # Mondo
    grid_w: int = 64
    grid_h: int = 64
    wilderness_margin: int = 24  # celle camminabili fuori dalla città
    obstacle_density: float = 0.08
    diagonal_movement: bool = False
    interaction_radius: float = 4.0      # celle
    study_required_ticks: int = 18

    # Telemetria
    log_path: str = "data/simulation_replay.msgpack"
    log_flush_every: int = 30
    parquet_out: str = "data/replay.parquet"

    # Checkpoint / recovery (operativi: non cambiano il mondo simulato)
    checkpoint_path: str = "data/simulation.checkpoint.msgpack"
    checkpoint_interval_ticks: int = 0  # 0 = disabilitato

    # LLM / cognizione — Hermes locale (llama.cpp, single RTX 4090).
    # Verificato live 2026-09-10: :8081/v1/models risponde con "qwable-9b"
    # (non qwen3-coder-30b-a3b — quel nome non e' mai stato caricato su questa
    # macchina, era un bug preesistente). Model/api_base corretti qui.
    # enabled resta False di default: con un modello live reale (anche a
    # temperature=0/seed fisso) due chiamate di rete separate su un
    # backend quantizzato non garantiscono byte identici — solo il fallback
    # deterministico (llm/router.py._fallback) lo garantisce. La rule
    # "replay bit-perfect" del progetto vale per default; live e' opt-in
    # via `--llm` (main.py) o settando questo flag esplicitamente.
    llm_enabled: bool = False
    llm_model: str = "qwable-9b"
    llm_api_base: str = "http://127.0.0.1:8081/v1"
    llm_timeout_s: float = 20.0
    llm_max_concurrency: int = 8
    llm_record_path: str = "data/llm_trace.jsonl"  # replay deterministico
    llm_api_key_env: str = "CIVITAS_LLM_API_KEY"
    llm_max_output_tokens: int = 256
    # Bugfix (2026-09-11, "gli agenti non si automigliorano"): un agente ha fino
    # a 9 eventi cognitivi "once-per-day" distinti (reflect/career/study/social/
    # exam/build/governance/room/research_focus — vedi i flag *_decided_day in
    # agents/state_machine.py) — con requests_per_agent=8 il budget si esauriva
    # PRIMA che arrivasse research_focus, chiamato per ultimo (subito dopo
    # reflect, nello stato REST a fine giornata): il research/discovery loop
    # (agents/research.py) finiva quasi sempre in fallback deterministico per
    # "budget_denied", non per un vero limite di costo. Margine per tutti e 9
    # gli eventi + un cuscinetto, non solo gli 8 più comuni.
    llm_daily_requests_per_agent: int = 12
    llm_daily_input_tokens_per_agent: int = 24_000
    llm_daily_output_tokens_per_agent: int = 4_000
    llm_daily_requests_global: int = 800
    llm_daily_input_tokens_global: int = 1_500_000
    llm_daily_output_tokens_global: int = 250_000
    reflection_batch: int = 12
    embed_dim: int = 384

    # Alveare RAG (operativo: non entra nel fingerprint mondo)
    alveare_url: str = ""  # es. http://127.0.0.1:9200
    alveare_frozen: bool = False  # True se CIVITAS_REPLAY=1

    # P1 ops
    metrics_enabled: bool = False
    metrics_port: int = 9100
    manifest_path: str = "data/run_manifest.json"
    sign_replay: bool = False
    otel_enabled: bool = False

    # P2 scale / telemetry
    spatial_hash_enabled: bool = False
    spatial_hash_cell_size: float = 4.0
    spatial_backend: str = "python"  # python | rust
    delta_log_enabled: bool = False
    delta_keyframe_every: int = 60
    cognitive_worker: bool = False

    # Paperclip-city (task board locale per eventi cognitivi)
    paperclip_city_enabled: bool = False
    paperclip_city_path: str = "data/paperclip_city"
    # Living City perpetua (operativo)
    living_mode: bool = False
    living_port: int = 9300
    # Autocostruzione città da progresso agenti (operativo; blueprints esterni in data/)
    city_growth_enabled: bool = True
    city_blueprints_dir: str = "data/city_blueprints"
    # Escrow builds (agent-funded Cafe/tower) — stile reel Civitas
    construction_enabled: bool = True
    agent_start_money: float = 50.0  # reel-parity: fondi iniziali per proporre
    # Governance/voting (Stage 6) + relocation POI esistenti (Stage 7) — reel-parity
    governance_enabled: bool = True
    # Ricerca internet reale nel research loop (Stage: crescita/apprendimento).
    # Off di default: fa chiamate di rete reali verso internet (non solo
    # localhost); on esplicitamente via --web-search o settando questo flag.
    web_search_enabled: bool = False
    web_search_trace_path: str = "data/web_search_trace.jsonl"
    vault_root: str = "vault"
    # Sindaco (provider LLM cloud separato da FreeLLM/Hermes, a scelta
    # dell'operatore): ratifica/veta le proposte chiuse dal voto popolare e
    # decide i pareggi (world/governance.py). Nessun default hardcoded verso
    # un provider specifico — configurare MAYOR_LLM_API_BASE/MAYOR_LLM_MODEL/
    # MAYOR_LLM_API_KEY nell'ambiente (vedi engine/tick_engine.py). Disabilitato
    # automaticamente se mancano, mai bloccante.
    mayor_enabled: bool = True
    mayor_model: str = ""
    mayor_api_base: str = ""
    mayor_api_key_env: str = "MAYOR_LLM_API_KEY"
    mayor_timeout_s: float = 20.0
    mayor_max_output_tokens: int = 256
    mayor_trace_path: str = "data/mayor_trace.jsonl"

    def simulation_dict(self) -> dict:
        """Solo i parametri che determinano il MONDO simulato.
        I percorsi di output e i parametri operativi sono esclusi cosi'
        due run con nomi di file diversi producono replay identici."""
        data = asdict(self)
        for key in (
            "log_path",
            "parquet_out",
            "llm_record_path",
            "log_flush_every",
            "llm_max_concurrency",
            "llm_timeout_s",
            "llm_api_key_env",
            "checkpoint_path",
            "checkpoint_interval_ticks",
            "total_ticks",  # durata del run, non regole del mondo
            "metrics_enabled",
            "metrics_port",
            "manifest_path",
            "sign_replay",
            "otel_enabled",
            "delta_log_enabled",
            "delta_keyframe_every",
            "cognitive_worker",
            "alveare_url",
            "alveare_frozen",
            "paperclip_city_enabled",
            "paperclip_city_path",
            "living_mode",
            "living_port",
            "city_growth_enabled",
            "city_blueprints_dir",
            "construction_enabled",
            "agent_start_money",
            "governance_enabled",
            "web_search_enabled",
            "web_search_trace_path",
            "vault_root",
            "mayor_trace_path",
            "mayor_timeout_s",
            "mayor_api_key_env",
        ):
            data.pop(key, None)
        return data

    def to_json(self) -> str:
        return json.dumps(self.simulation_dict(), sort_keys=True, ensure_ascii=False)

    def fingerprint(self) -> str:
        import hashlib
        payload = self.to_json() + "|" + json.dumps(POIS, sort_keys=True)
        payload += "|" + json.dumps(DEFAULT_SCHEDULE) + "|" + json.dumps(COURSES, sort_keys=True)
        payload += "|" + json.dumps(JOBS, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
