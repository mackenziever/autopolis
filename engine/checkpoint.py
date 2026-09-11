"""Checkpoint atomici, verificati e indipendenti dal registro eventi.

Il checkpoint rappresenta lo stato necessario a riprendere dal `next_tick`.
Scrittura: tempfile nella stessa directory -> flush/fsync -> os.replace -> fsync dir.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import msgpack

from agents.memory import MemoryItem
from agents.models import AgentState

CHECKPOINT_SCHEMA = 1


class CheckpointError(RuntimeError):
    pass


def _pack(obj: dict) -> bytes:
    return msgpack.packb(obj, use_bin_type=True, strict_types=False)


def _agent_dump(agent) -> dict:
    r, c = agent.r, agent.cog
    return {
        "agent_id": r.agent_id,
        "number": r.number,
        "position": list(r.position),
        "state": str(r.state),
        "previous_state": str(r.previous_state),
        "target_poi": r.target_poi,
        "path": [list(x) for x in r.path],
        "energy": r.energy,
        "hunger": r.hunger,
        "money": r.money,
        "job": r.job,
        "skills": list(r.skills),
        "study_progress": dict(r.study_progress),
        "relationships": dict(r.relationships),
        "last_thought": r.last_thought,
        "exam_attempted_day": r.exam_attempted_day,
        "reflected_day": r.reflected_day,
        "active_course": r.active_course or r.persona.preferred_course,
        "career_decided_day": r.career_decided_day,
        "study_focused_day": r.study_focused_day,
        "social_decided_day": r.social_decided_day,
        "build_decided_day": r.build_decided_day,
        "room_decided_day": r.room_decided_day,
        "research_decided_day": r.research_decided_day,
        "governance_decided_day": r.governance_decided_day,
        "strategy": c.strategy,
        "improve_focus": getattr(c.improve, "focus", "study"),
        "improve_lessons": list(getattr(c.improve, "lessons", []) or []),
        "hard_case_streak": dict(getattr(c, "hard_case_streak", {}) or {}),
        "posture_experience": (
            c.posture_experience.to_state() if getattr(c, "posture_experience", None) is not None else {}
        ),
        "last_posture": getattr(c, "_last_posture", None),
        "escalation_gate": (
            c.escalation_gate.to_state() if getattr(c, "escalation_gate", None) is not None else {}
        ),
        "memories": [asdict(m) for m in c.memory.items],
    }


def capture(engine, next_tick: int) -> dict:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "fingerprint": engine.cfg.fingerprint(),
        "next_tick": int(next_tick),
        "agents": [_agent_dump(a) for a in engine.agents],
        "economy": dict(engine.economy.hires_by_role),
        "social_last": [[a, b, tick] for (a, b), tick in sorted(engine.social.last.items())],
        "budget": engine.router.budget.snapshot(),
        "construction": (
            engine.construction.to_state() if getattr(engine, "construction", None) is not None else None
        ),
        "rooms": (
            engine.rooms.to_state() if getattr(engine, "rooms", None) is not None else None
        ),
        "governance": (
            engine.governance.to_state() if getattr(engine, "governance", None) is not None else None
        ),
    }


def save_atomic(path: str, engine, next_tick: int) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = capture(engine, next_tick)
    raw = _pack(payload)
    envelope = _pack({"sha256": hashlib.sha256(raw).hexdigest(), "payload": raw})
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(envelope)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
        try:
            dfd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return hashlib.sha256(envelope).hexdigest()


def load(path: str, expected_fingerprint: str | None = None) -> dict:
    try:
        envelope = msgpack.unpackb(Path(path).read_bytes(), raw=False, strict_map_key=False)
        raw, expected = envelope["payload"], envelope["sha256"]
    except Exception as exc:
        raise CheckpointError(f"Checkpoint illeggibile: {exc}") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise CheckpointError("Checksum checkpoint non valido")
    payload = msgpack.unpackb(raw, raw=False, strict_map_key=False)
    if payload.get("schema") != CHECKPOINT_SCHEMA:
        raise CheckpointError(f"Schema checkpoint non supportato: {payload.get('schema')}")
    if expected_fingerprint and payload.get("fingerprint") != expected_fingerprint:
        raise CheckpointError("Fingerprint config incompatibile con il checkpoint")
    return payload


def restore(engine, payload: dict) -> int:
    by_id = {a.r.agent_id: a for a in engine.agents}
    if set(by_id) != {x["agent_id"] for x in payload["agents"]}:
        raise CheckpointError("Popolazione checkpoint incompatibile")
    for item in payload["agents"]:
        a = by_id[item["agent_id"]]
        r, c = a.r, a.cog
        r.position = tuple(item["position"])
        r.state = AgentState(item["state"])
        r.previous_state = AgentState(item["previous_state"])
        r.target_poi = item["target_poi"]
        r.path = [tuple(x) for x in item["path"]]
        r.energy = float(item["energy"])
        r.hunger = float(item["hunger"])
        r.money = float(item["money"])
        r.job = item["job"]
        r.skills = list(item["skills"])
        r.study_progress = dict(item["study_progress"])
        r.relationships = {str(k): float(v) for k, v in item["relationships"].items()}
        r.last_thought = item["last_thought"]
        r.exam_attempted_day = int(item["exam_attempted_day"])
        r.reflected_day = int(item["reflected_day"])
        r.active_course = str(item.get("active_course") or r.persona.preferred_course)
        r.career_decided_day = int(item.get("career_decided_day", -1))
        r.study_focused_day = int(item.get("study_focused_day", -1))
        r.social_decided_day = int(item.get("social_decided_day", -1))
        r.build_decided_day = int(item.get("build_decided_day", -1))
        r.room_decided_day = int(item.get("room_decided_day", -1))
        r.research_decided_day = int(item.get("research_decided_day", -1))
        r.governance_decided_day = int(item.get("governance_decided_day", -1))
        c.strategy = item["strategy"]
        if hasattr(c, "improve") and item.get("improve_focus"):
            c.improve.focus = str(item["improve_focus"])
        if hasattr(c, "improve") and "improve_lessons" in item:
            c.improve.lessons = list(item.get("improve_lessons") or [])
        if hasattr(c, "hard_case_streak"):
            c.hard_case_streak = {
                str(k): int(v) for k, v in (item.get("hard_case_streak") or {}).items()
            }
        if getattr(c, "posture_experience", None) is not None:
            c.posture_experience.load_state(item.get("posture_experience") or {})
        if hasattr(c, "_last_posture"):
            c._last_posture = item.get("last_posture")
        if getattr(c, "escalation_gate", None) is not None:
            c.escalation_gate.load_state(item.get("escalation_gate") or {})
        c.memory.items = [MemoryItem(**m) for m in item["memories"]]
        c.memory.vectors = {
            m.key: c.memory.embedder.encode(m.text) for m in c.memory.items
        }
        c.memory._rebuild()
    engine.economy.hires_by_role.clear()
    engine.economy.hires_by_role.update(payload["economy"])
    engine.social.last = {(a, b): int(tick) for a, b, tick in payload["social_last"]}
    engine.router.budget.restore(payload.get("budget", {}))
    if payload.get("construction") is not None and getattr(engine, "construction", None) is not None:
        engine.construction.load_state(payload["construction"])
    if payload.get("rooms") is not None and getattr(engine, "rooms", None) is not None:
        engine.rooms.load_state(payload["rooms"])
    if payload.get("governance") is not None and getattr(engine, "governance", None) is not None:
        engine.governance.load_state(payload["governance"])
    return int(payload["next_tick"])
