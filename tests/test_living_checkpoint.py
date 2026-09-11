"""Living City deve salvare/riprendere progresso tra restart (docker compose
restart/up), non azzerare gli agenti ad ogni riavvio del servizio 'living'."""
from __future__ import annotations

import asyncio
import os

from config import SimConfig
from engine.tick_engine import CivitasEngine
from living_server.day_loop import run_day_loop


def _cfg(tmp_path, name, seed=7):
    return SimConfig(
        num_agents=3,
        total_ticks=10**9,
        day_length_ticks=10,
        tick_rate_hz=15,
        seed=seed,
        log_path=str(tmp_path / f"{name}.msgpack"),
        llm_record_path=str(tmp_path / f"{name}.jsonl"),
    )


def test_day_loop_checkpoints_at_day_boundary_and_resumes(tmp_path):
    ckpt = str(tmp_path / "living.checkpoint.msgpack")
    engine = CivitasEngine(_cfg(tmp_path, "a"))
    stop = asyncio.Event()
    result = asyncio.run(
        run_day_loop(
            engine,
            stop_event=stop,
            realtime=False,
            max_ticks=25,  # attraversa 2 confini di giorno (day_length_ticks=10)
            session_dir=str(tmp_path / "vault"),
            checkpoint_path=ckpt,
        )
    )
    assert result["days"] >= 2
    assert os.path.isfile(ckpt)

    # Stato reale dell'engine originale all'ultimo confine di giorno salvato
    # (day=2 -> tick 20, salvato con next_tick=21 dal loop).
    original_positions = {a.r.agent_id: a.r.position for a in engine.agents}
    original_money = {a.r.agent_id: a.r.money for a in engine.agents}

    resumed = CivitasEngine(_cfg(tmp_path, "b"))
    start = resumed.resume_from(ckpt)
    assert 0 < start <= 25

    # Il resume deve riportare ESATTAMENTE lo stato salvato, non agenti freschi:
    # se la persistenza fosse rotta, position/money sarebbero quelli iniziali
    # (stessa griglia Home/seed) invece di coincidere con l'engine originale.
    for a in resumed.agents:
        assert a.r.position == original_positions[a.r.agent_id]
        assert a.r.money == original_money[a.r.agent_id]
