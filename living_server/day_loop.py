"""Day loop perpetuo per Living City AGI-OS."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from engine.checkpoint import save_atomic
from engine.tick_engine import CivitasEngine

EventHook = Callable[[int, list], Awaitable[None] | None]

# Once-per-day FSM flags on AgentRuntime (see agents/state_machine.py).
# Each decision fires when stored_day != current_day (tick // day_length).
# Crossing a day boundary therefore re-enables reflect / career / study / social /
# exam WITHOUT resetting flags mid-day (preserves determinism and checkpoint fidelity).
DAY_DECISION_FLAG_ATTRS = (
    "reflected_day",
    "career_decided_day",
    "study_focused_day",
    "social_decided_day",
    "exam_attempted_day",
    "build_decided_day",
)


def daily_decision_pending(stored_day: int, current_day: int) -> bool:
    """True when FSM should allow another once-per-day decision for ``current_day``."""
    return stored_day != current_day


def agents_ready_for_new_day(agents: list, day: int) -> bool:
    """Contract: after a day increment, every agent can reflect again (day-keyed FSM)."""
    return all(daily_decision_pending(a.r.reflected_day, day) for a in agents)


async def run_day_loop(
    engine: CivitasEngine,
    *,
    stop_event: asyncio.Event,
    realtime: bool = True,
    on_tick: Optional[EventHook] = None,
    session_dir: str | Path = "vault/05-SESSIONS",
    max_ticks: int | None = None,
    checkpoint_path: str | None = None,
) -> dict[str, Any]:
    """Ciclo continuo: ogni giorno gli AGI-OS riflettono di nuovo (day = tick // day_len).

    Se `checkpoint_path` e' dato, salva uno snapshot atomico ad ogni confine di
    giorno E allo shutdown (SIGTERM/stop_event), cosi' un riavvio del
    container (`docker compose up`/restart) riprende da dove erano rimasti gli
    agenti invece di azzerarli — il servizio 'living' e' pensato per girare
    indefinitamente, quindi senza questo i progressi si perdono ad ogni
    restart. Stesso `engine.checkpoint.save_atomic` gia' usato/testato da
    `main.py --checkpoint-every`."""
    period = 1 / engine.cfg.tick_rate_hz
    tick = engine.start_tick
    wall0 = time.perf_counter()
    days_done = 0
    last_day = tick // engine.cfg.day_length_ticks

    print(
        f"[LIVING] start tick={tick} agents={len(engine.agents)} "
        f"llm={engine.cfg.llm_enabled} alveare={bool(engine.alveare)}"
    )
    try:
        while not stop_event.is_set():
            if max_ticks is not None and (tick - engine.start_tick) >= max_ticks:
                break
            t0 = time.perf_counter()
            events = await engine.step_one_tick(tick)
            if on_tick:
                maybe = on_tick(tick, events)
                if asyncio.iscoroutine(maybe):
                    await maybe
            day = tick // engine.cfg.day_length_ticks
            if day > last_day:
                days_done += 1
                last_day = day
                # No mid-day flag reset: AgentFSM keys off reflected_day != day, etc.
                if not agents_ready_for_new_day(engine.agents, day):
                    print(
                        f"[LIVING] warn day={day}: reflected_day already equals new day "
                        f"(unexpected; check checkpoint / clock)"
                    )
                _append_session_note(
                    session_dir,
                    day=day,
                    tick=tick,
                    agents=len(engine.agents),
                    llm=dict(engine.router.stats),
                )
                engine.alveare_batch.flush()
                if checkpoint_path:
                    try:
                        save_atomic(checkpoint_path, engine, next_tick=tick + 1)
                    except OSError as exc:
                        print(f"[LIVING] checkpoint save failed day={day}: {exc}")
            dt = time.perf_counter() - t0
            engine.metrics.observe("civitas_tick_seconds", dt)
            engine.metrics.inc("civitas_ticks_total")
            if realtime:
                await asyncio.sleep(max(0.0, period - dt))
            tick += 1
    finally:
        if checkpoint_path:
            try:
                save_atomic(checkpoint_path, engine, next_tick=tick)
            except OSError as exc:
                print(f"[LIVING] checkpoint save on shutdown failed: {exc}")
        if engine.cognitive_worker:
            await engine.cognitive_worker.stop()
        engine.logger.close()
        engine.publisher.close()
        if engine._metrics_server:
            engine._metrics_server.stop()

    return {
        "ticks": tick - engine.start_tick,
        "end_tick": tick,
        "days": days_done,
        "wall_seconds": time.perf_counter() - wall0,
        "llm": dict(engine.router.stats),
    }


def _append_session_note(session_dir: str | Path, *, day: int, tick: int, agents: int, llm: dict) -> None:
    try:
        root = Path(session_dir)
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = root / f"{stamp}-living-day-{day}.md"
        line = (
            f"\n- day={day} tick={tick} agents={agents} "
            f"llm_live={llm.get('live')} fallback={llm.get('fallback')} errors={llm.get('errors')}\n"
        )
        if not path.exists():
            path.write_text(
                f"---\ntags: [living, session]\nday: {day}\n---\n\n# Living day {day}\n",
                encoding="utf-8",
            )
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError as exc:
        # Perpetual loop must not die if vault mount is read-only or disk full.
        print(f"[LIVING] session note failed day={day}: {exc}")
