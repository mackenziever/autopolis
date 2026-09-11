"""Single-writer deterministic tick engine, separato da UI e inferenza."""
from __future__ import annotations

import asyncio
import os
import random
import time
from typing import Dict

import numpy as np

from agents.cognitive import AgentCognitiveEngine
from agents.mayor import MayorOffice
from agents.models import AgentRuntime, AgentState
from agents.persona import generate_persona
from agents.research import ResearchLoop
from agents.state_machine import AgentFSM
from config import DEFAULT_SCHEDULE, POIS, SimConfig
from engine.checkpoint import load as load_checkpoint
from engine.checkpoint import restore as restore_checkpoint
from engine.checkpoint import save_atomic
from engine.spatial_backend import make_spatial_backend
from knowledge.batch import AlveareBatchBuffer
from knowledge.client import AlveareClient
from knowledge.vault_librarian import VaultLibrarian
from knowledge.web_search import WebSearchClient
from llm.cognitive_worker import CognitiveWorker
from llm.router import CognitiveRouter
from metrics.collector import GLOBAL_COLLECTOR
from metrics.otel import OTelBridge
from metrics.server import MetricsServer
from security.hmac_replay import sign_file
from telemetry.bus import TelemetryPublisher
from telemetry.delta_logger import DeltaTelemetryLogger
from telemetry.logger import BinaryTelemetryLogger
from telemetry.manifest import write_run_manifest
from paperclip_city.board import Board
from paperclip_city.heartbeat import run_heartbeat
from world.city_growth import CityGrowthEngine
from world.construction import ConstructionBoard
from world.economy import LaborMarket
from world.governance import GovernanceBoard
from world.map import CityMap
from world.room_board import RoomBoard
from world.social import SocialSystem


class CivitasEngine:
    def __init__(self, cfg: SimConfig, live_endpoint: str | None = None):
        self.cfg = cfg
        random.seed(cfg.seed)
        np.random.seed(cfg.seed)
        self.city = CityMap(
            cfg.grid_w,
            cfg.grid_h,
            cfg.seed,
            cfg.obstacle_density,
            wilderness_margin=getattr(cfg, "wilderness_margin", 24),
        )
        self.city_growth = None
        if getattr(cfg, "city_growth_enabled", True):
            self.city_growth = CityGrowthEngine.load(
                cfg.seed,
                extra_dir=getattr(cfg, "city_blueprints_dir", "data/city_blueprints"),
                enabled=True,
            )
        self.construction = None
        if getattr(cfg, "construction_enabled", True):
            self.construction = ConstructionBoard(cfg.seed, cfg.day_length_ticks)
        self.rooms = RoomBoard(cfg.seed)
        self.rooms.seed_pois(list(self.city.pois.keys()))
        self.governance = None
        if getattr(cfg, "governance_enabled", True):
            self.governance = GovernanceBoard(cfg.seed, cfg.day_length_ticks)
        self.mayor = None
        mayor_api_base = os.getenv("MAYOR_LLM_API_BASE") or getattr(cfg, "mayor_api_base", "")
        mayor_model = os.getenv("MAYOR_LLM_MODEL") or getattr(cfg, "mayor_model", "")
        if (
            self.governance is not None
            and getattr(cfg, "mayor_enabled", True)
            and getattr(cfg, "mayor_api_key_env", "")
            and os.getenv(cfg.mayor_api_key_env)
            and mayor_api_base
            and mayor_model
        ):
            # Provider separato da FreeLLM/Hermes (agents/cognitive.py usa
            # self.router): un servizio cloud a pagamento a scelta
            # dell'operatore, quindi il sindaco ha il proprio
            # CognitiveRouter/trace/cache, mai condiviso con quello dei
            # cittadini. Se chiave/endpoint/modello mancano, self.mayor resta
            # None e world/governance.py.tick_day() si comporta esattamente
            # come prima (yes > no decide, pareggio = non passa) — mai bloccante.
            mayor_router = CognitiveRouter(
                True,
                mayor_model,
                mayor_api_base,
                cfg.mayor_timeout_s,
                1,
                cfg.mayor_trace_path,
                cfg.seed,
                day_length=cfg.day_length_ticks,
                max_output_tokens=cfg.mayor_max_output_tokens,
                api_key_env=cfg.mayor_api_key_env,
                # Tetto di sicurezza contro un bug che chiami il sindaco in loop
                # (provider a pagamento, non free-tier come FreeLLM) — ben oltre
                # MAX_ACTIVE_PROPOSALS=3 chiusure/giorno attese in condizioni normali.
                requests_per_agent=50,
                input_per_agent=200_000,
                output_per_agent=50_000,
                global_requests=50,
                global_input=200_000,
                global_output=50_000,
            )
            self.mayor = MayorOffice(mayor_router)
        self.spatial_backend = make_spatial_backend(
            self.city,
            backend=cfg.spatial_backend,
            diagonal=cfg.diagonal_movement,
            use_hash=cfg.spatial_hash_enabled,
            cell=cfg.spatial_hash_cell_size,
        )
        # Compat: AgentFSM usa SpatialService.astar — preferisci service del backend.
        self.spatial = getattr(self.spatial_backend, "service", None)
        if self.spatial is None:
            from engine.spatial import SpatialService

            self.spatial = SpatialService(self.city, cfg.diagonal_movement)
        self.spatial_hash = getattr(self.spatial_backend, "hash", None)
        self.economy = LaborMarket()
        self.social = SocialSystem()
        self.router = CognitiveRouter(
            cfg.llm_enabled,
            cfg.llm_model,
            cfg.llm_api_base,
            cfg.llm_timeout_s,
            cfg.llm_max_concurrency,
            cfg.llm_record_path,
            cfg.seed,
            day_length=cfg.day_length_ticks,
            max_output_tokens=cfg.llm_max_output_tokens,
            api_key_env=cfg.llm_api_key_env,
            requests_per_agent=cfg.llm_daily_requests_per_agent,
            input_per_agent=cfg.llm_daily_input_tokens_per_agent,
            output_per_agent=cfg.llm_daily_output_tokens_per_agent,
            global_requests=cfg.llm_daily_requests_global,
            global_input=cfg.llm_daily_input_tokens_global,
            global_output=cfg.llm_daily_output_tokens_global,
        )
        self.alveare = None
        if cfg.alveare_url:
            self.alveare = AlveareClient(cfg.alveare_url, frozen=bool(cfg.alveare_frozen))
        self.alveare_batch = AlveareBatchBuffer(self.alveare, frozen=bool(cfg.alveare_frozen))
        self.librarian = VaultLibrarian(
            vault_root=getattr(cfg, "vault_root", None) or "vault",
            alveare=self.alveare,
        )
        self.web_search = None
        if getattr(cfg, "web_search_enabled", False):
            self.web_search = WebSearchClient(
                trace_path=getattr(cfg, "web_search_trace_path", "data/web_search_trace.jsonl"),
                frozen=bool(cfg.alveare_frozen),
            )
        self.research = ResearchLoop(
            self.router, self.librarian, alveare=self.alveare, web_search=self.web_search
        )
        self.cognitive_worker = None
        if cfg.cognitive_worker:
            self.cognitive_worker = CognitiveWorker(self.router.decide).start()
        self.paperclip_board = None
        if cfg.paperclip_city_enabled:
            self.paperclip_board = Board(cfg.paperclip_city_path, cfg.seed)
        self.publisher = TelemetryPublisher(live_endpoint)
        self.metrics = GLOBAL_COLLECTOR
        self.otel = OTelBridge(enabled=bool(cfg.otel_enabled))
        self._metrics_server = None
        if cfg.metrics_enabled:
            self._metrics_server = MetricsServer(
                port=cfg.metrics_port,
                health_extra=self._health_extra,
            ).start()
            self.cfg.metrics_port = self._metrics_server.port
        self.runtimes: Dict[str, AgentRuntime] = {}
        self.agents = []
        for n in range(cfg.num_agents):
            aid = f"agent_{n:03d}"
            persona = generate_persona(n, cfg.seed)
            start = self.city.slot_near("Home", n, 3)
            r = AgentRuntime(aid, n, persona, start)
            start_money = float(getattr(cfg, "agent_start_money", 20.0) or 20.0)
            r.money = start_money
            self.runtimes[aid] = r
            cog = AgentCognitiveEngine(
                r,
                self.router,
                cfg.seed,
                cfg.embed_dim,
                alveare=self.alveare,
                alveare_batch=self.alveare_batch,
            )
            self.agents.append(
                AgentFSM(
                    r,
                    cog,
                    self.spatial,
                    self.economy,
                    cfg.day_length_ticks,
                    cfg.study_required_ticks,
                    paperclip_board=self.paperclip_board,
                    construction=self.construction,
                    governance=self.governance,
                    rooms=self.rooms,
                    research=self.research,
                )
            )
            cog.agi_os.paperclip_board = self.paperclip_board
            cog.agi_os.bind_improve(cog.improve)
            cog.agi_os.set_strategy(cog.strategy)
        m = self.city.snapshot()
        metadata = {
            "config": cfg.to_json(),
            "fingerprint": cfg.fingerprint(),
            "seed": cfg.seed,
            "agents": cfg.num_agents,
            "tick_rate_hz": cfg.tick_rate_hz,
            "grid": [cfg.grid_w, cfg.grid_h],
            "pois": {k: list(v) for k, v in self.city.pois.items()},
            "blocked": [list(c) for c in m.blocked_cells],
            "delta_log": bool(cfg.delta_log_enabled),
            "spatial_hash": bool(cfg.spatial_hash_enabled),
            "spatial_backend": cfg.spatial_backend,
            "city_growth": bool(self.city_growth),
        }
        self.metadata = metadata
        if cfg.delta_log_enabled:
            self.logger = DeltaTelemetryLogger(
                cfg.log_path, metadata, cfg.log_flush_every, cfg.delta_keyframe_every
            )
        else:
            self.logger = BinaryTelemetryLogger(cfg.log_path, metadata, cfg.log_flush_every)
        self.start_tick = 0

    def _health_extra(self) -> dict:
        extra = {
            "fingerprint": self.cfg.fingerprint(),
            "agents": len(self.agents),
            "llm_enabled": self.cfg.llm_enabled,
            "log_path": self.cfg.log_path,
            "zmq_sent": self.publisher.sent,
            "zmq_dropped": self.publisher.dropped,
            "alveare": bool(self.alveare),
            "paperclip_city": bool(self.paperclip_board),
        }
        if self.paperclip_board is not None:
            extra.update(self.paperclip_board.stats())
        if getattr(self.cfg, "living_mode", False):
            extra["living"] = True
            extra["agi_os"] = len(self.agents)
        if self.city_growth is not None:
            snap = self.city_growth.snapshot()
            extra["city_built"] = len(snap.get("built") or [])
            extra["city_metrics"] = snap.get("metrics")
        if self.construction is not None:
            cs = self.construction.snapshot()
            extra["construction"] = cs.get("stats")
            extra["agent_builds"] = len(cs.get("completed_pois") or [])
        if getattr(self, "rooms", None) is not None:
            rs = self.rooms.snapshot()
            extra["rooms"] = rs.get("stats")
            extra["room_count"] = len(rs.get("rooms") or {})
        if self.governance is not None:
            extra["governance"] = self.governance.snapshot().get("stats")
        extra["mayor_enabled"] = self.mayor is not None
        if self.mayor is not None:
            extra["mayor"] = dict(self.mayor.stats)
        if self.web_search is not None:
            extra["web_search"] = dict(self.web_search.stats)
        if getattr(self, "research", None) is not None:
            extra["research"] = dict(self.research.stats)
            extra["research_rates"] = self.research.stats_summary()
        active_hard_cases = [
            (a.r.agent_id, topic, n)
            for a in self.agents
            for topic, n in getattr(a.cog, "hard_case_streak", {}).items()
        ]
        extra["hard_case_mining"] = {
            "agents_with_active_streak": len({row[0] for row in active_hard_cases}),
            "total_active_topics": len(active_hard_cases),
            "max_streak": max((row[2] for row in active_hard_cases), default=0),
        }
        extra["escalation"] = {
            "agents_escalated_now": sum(
                1 for a in self.agents if getattr(a.cog, "escalation_gate", None) and a.cog.escalation_gate.is_active
            ),
            "tier0_skipped_total": self.router.stats.get("tier0_skipped_escalation", 0),
        }
        # Telemetria end-to-end (consiglio esterno, 2026-09-11, "5.
        # Telemetry"): tassi derivati dal router LLM + latenza tick, per
        # notare un degrado (free-tier instabile, tick lenti) da /health senza
        # dover interrogare i log grezzi.
        extra["llm_rates"] = self.router.stats_summary()
        tick_s = GLOBAL_COLLECTOR.summary("civitas_tick_seconds")
        extra["tick_duration_ms"] = {
            "count": tick_s["count"],
            "mean": round(tick_s["mean"] * 1000, 3),
            "p95": round(tick_s["p95"] * 1000, 3),
            "last": round(tick_s["last"] * 1000, 3),
        }
        extra["building_relocation_conflicts"] = GLOBAL_COLLECTOR.get_counter(
            "civitas_building_relocation_conflicts_total"
        )
        return extra

    def resume_from(self, checkpoint_path: str) -> int:
        payload = load_checkpoint(checkpoint_path, self.cfg.fingerprint())
        self.start_tick = restore_checkpoint(self, payload)
        return self.start_tick

    def scheduled_state(self, tick: int, agent_number: int) -> AgentState:
        offset = (agent_number * 7 + self.cfg.seed) % 13 - 6
        local = (tick - offset) % self.cfg.day_length_ticks
        state = AgentState(DEFAULT_SCHEDULE[0][1])
        for start, name in DEFAULT_SCHEDULE:
            if local >= start:
                state = AgentState(name)
            else:
                break
        return state

    def _pairs_near(self, positions: Dict[str, tuple]) -> list:
        return self.spatial_backend.all_pairs_near(positions, self.cfg.interaction_radius)

    def agi_os_snapshots(self) -> list:
        out = []
        for a in self.agents:
            a.cog.agi_os.set_strategy(a.cog.strategy)
            a.cog.agi_os.paperclip_board = self.paperclip_board
            out.append(a.cog.agi_os.heartbeat_state())
        return out

    def agi_os_one(self, agent_id: str) -> dict | None:
        for a in self.agents:
            if a.r.agent_id == agent_id:
                a.cog.agi_os.set_strategy(a.cog.strategy)
                a.cog.agi_os.paperclip_board = self.paperclip_board
                st = a.cog.agi_os.heartbeat_state()
                st["soul_excerpt"] = a.cog.agi_os.soul_excerpt()[:800]
                st["recent_memories"] = [
                    {"kind": m.kind, "text": m.text, "tick": m.tick}
                    for m in a.cog.memory.recent(8)
                ]
                return st
        return None

    async def step_one_tick(self, tick: int) -> list:
        """Esegue un tick e ritorna gli eventi (per Living Server)."""
        if self.paperclip_board is not None and (
            tick == self.start_tick or tick % self.cfg.day_length_ticks == 0
        ):
            day = tick // self.cfg.day_length_ticks
            await run_heartbeat(
                self.paperclip_board,
                self.agents,
                day,
                tick,
                cognitive_worker=self.cognitive_worker,
                cfg=self.cfg,
                governance=self.governance,
            )
        reserved = {r.position for r in self.runtimes.values()}
        events = []
        for a in self.agents:
            reserved.discard(a.r.position)
            events.extend(
                await a.step(tick, self.scheduled_state(tick, a.r.number), reserved)
            )
            reserved.add(a.r.position)
        positions = {aid: r.position for aid, r in self.runtimes.items()}
        pairs = self._pairs_near(positions)
        events.extend(self.social.process(tick, pairs, self.runtimes))
        day = tick // self.cfg.day_length_ticks
        if self.construction is not None:
            # Completa progetti escrow (e rilocazioni) quando fondi+giorni ok
            events.extend(self.construction.tick_day(day, tick, self.city))
            if any(e.get("type") in ("city_build", "relocate_completed") for e in events):
                self.metadata["pois"] = {k: list(v) for k, v in self.city.pois.items()}
            for ev in events:
                if ev.get("type") == "city_build" and ev.get("poi") and self.rooms is not None:
                    self.rooms.ensure_room(str(ev["poi"]))
        if self.governance is not None:
            mayor_rulings = {}
            if self.mayor is not None:
                for prop in self.governance.proposals_closing_now(tick):
                    yes, no, abstain = self.governance.tally(prop)
                    if yes < no:
                        # Gia' respinta chiaramente dal popolo: il sindaco ha
                        # potere di ratifica/tie-break, non di ribaltare un
                        # rigetto — non interpellarlo, resta "rejected" come
                        # senza sindaco (world/governance.py.tick_day()).
                        continue
                    mayor_rulings[prop.proposal_id] = await self.mayor.rule_on_proposal(
                        tick, prop, yes=yes, no=no, abstain=abstain
                    )
            # Chiude le proposte scadute, applica le ordinanze passate
            events.extend(
                self.governance.tick_day(day, tick, mayor_rulings=mayor_rulings or None)
            )
        if self.city_growth is not None:
            # End of tick: progresso collettivo → eventuale costruzione POI
            # (una build max per tick; A* resta LLM-free).
            events.extend(
                self.city_growth.step(tick, self.agents, events, self.city)
            )
            # Metadata pois aggiornati per snapshot viewer
            if any(e.get("type") == "city_build" for e in events):
                self.metadata["pois"] = {k: list(v) for k, v in self.city.pois.items()}
                for ev in events:
                    if ev.get("type") == "city_build" and ev.get("poi") and self.rooms is not None:
                        self.rooms.ensure_room(str(ev["poi"]))
        self.alveare_batch.flush()
        if (
            self.cfg.checkpoint_interval_ticks > 0
            and (tick + 1) % self.cfg.checkpoint_interval_ticks == 0
        ):
            digest = save_atomic(self.cfg.checkpoint_path, self, tick + 1)
            events.append(
                {
                    "type": "checkpoint",
                    "tick": tick,
                    "next_tick": tick + 1,
                    "sha256": digest,
                }
            )
        self.logger.log_tick(tick, tick / self.cfg.tick_rate_hz, events)
        snaps = [e for e in events if e["type"] == "snapshot"]
        self.publisher.publish(tick, snaps)
        for e in events:
            if e.get("type") in (
                "reflection",
                "career_decision",
                "study_decision",
                "social_decision",
                "exam_result",
                "job_change",
                "city_build",
                "build_propose",
                "build_contribute",
                "build_decision",
                "room_decision",
                "room_apply",
                "room_reject",
                "research_decision",
                "governance_decision",
                "proposal_submitted",
                "vote_cast",
                "proposal_closed",
                "mayor_ruling",
                "relocate_proposed",
                "relocate_crew_joined",
                "relocate_completed",
                "relocate_failed",
            ):
                aid = e.get("agent_id")
                if aid and aid in self.runtimes:
                    for a in self.agents:
                        if a.r.agent_id == aid:
                            a.cog.agi_os.record_event(e)
                            break
                # Persistenza organizzata vault (tutti gli agenti)
                try:
                    self.research.curate_event(e)
                except Exception:
                    pass
        return events

    async def run(self, total_ticks: int | None = None, realtime: bool = True):
        total = total_ticks or self.cfg.total_ticks
        period = 1 / self.cfg.tick_rate_hz
        wall0 = time.perf_counter()
        compute = []
        overruns = 0
        print(
            f"[ENGINE] agenti={len(self.agents)} seed={self.cfg.seed} "
            f"target={self.cfg.tick_rate_hz}Hz start={self.start_tick} "
            f"spatial_hash={bool(self.spatial_hash)} backend={self.cfg.spatial_backend} "
            f"delta_log={self.cfg.delta_log_enabled}"
        )
        try:
            with self.otel.span("civitas.run", agents=len(self.agents), seed=self.cfg.seed):
                for tick in range(self.start_tick, total):
                    t0 = time.perf_counter()
                    await self.step_one_tick(tick)
                    dt = time.perf_counter() - t0
                    compute.append(dt)
                    if dt > period:
                        overruns += 1
                        self.metrics.inc("civitas_tick_overruns_total")
                    self.metrics.observe("civitas_tick_seconds", dt)
                    self.metrics.inc("civitas_ticks_total")
                    self.metrics.set_gauge("civitas_agents", float(len(self.agents)))
                    if realtime:
                        await asyncio.sleep(max(0, period - dt))
        finally:
            if self.cognitive_worker:
                await self.cognitive_worker.stop()
            self.logger.close()
            self.publisher.close()
            if self._metrics_server:
                self._metrics_server.stop()
        wall = time.perf_counter() - wall0
        p95 = (
            sorted(compute)[min(len(compute) - 1, int(len(compute) * 0.95))] * 1000
            if compute
            else 0
        )
        completed = max(0, total - self.start_tick)
        hmac_digest = None
        if self.cfg.sign_replay:
            try:
                hmac_digest = sign_file(self.cfg.log_path)
            except Exception as exc:
                hmac_digest = f"error:{exc}"
        cache = getattr(self.spatial_backend, "cache_stats", {}) or {}
        perf = {
            "overruns": overruns,
            "path_cache": cache,
            "log_bytes": getattr(self.logger, "bytes_written", 0),
            "zmq_dropped": self.publisher.dropped,
            "cognitive_worker": getattr(self.cognitive_worker, "stats", None),
        }
        self.metrics.set_gauge("civitas_log_bytes", float(perf["log_bytes"]))
        self.metrics.set_gauge("civitas_path_cache_hits", float(cache.get("hits", 0)))
        manifest = write_run_manifest(
            path=self.cfg.manifest_path,
            cfg_fingerprint=self.cfg.fingerprint(),
            seed=self.cfg.seed,
            agents=len(self.agents),
            ticks_completed=completed,
            log_path=self.cfg.log_path,
            extra={
                "hmac": hmac_digest,
                "spatial_hash": bool(self.spatial_hash),
                "spatial_backend": self.cfg.spatial_backend,
                "delta_log": getattr(self.logger, "stats", None),
                "llm": dict(self.router.stats),
                "perf": perf,
            },
        )
        result = {
            "ticks": completed,
            "start_tick": self.start_tick,
            "end_tick": total,
            "wall_seconds": wall,
            "wall_hz": completed / wall if wall else 0,
            "compute_mean_ms": 1000 * sum(compute) / len(compute) if compute else 0,
            "compute_p95_ms": p95,
            "llm": dict(self.router.stats),
            "spatial_hash": bool(self.spatial_hash),
            "spatial_backend": self.cfg.spatial_backend,
            "delta_log": getattr(self.logger, "stats", None),
            "metrics_port": self.cfg.metrics_port if self.cfg.metrics_enabled else None,
            "manifest": manifest,
            "hmac": hmac_digest,
            "perf": perf,
        }
        print("[ENGINE]", result)
        return result
