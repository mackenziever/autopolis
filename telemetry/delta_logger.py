"""Keyframe + delta snapshot logger per ridurre la dimensione del registro.

Il formato resta framed MessagePack. I tick non-keyframe trasportano solo i
campi snapshot cambiati rispetto allo stato precedente; header/footer invariati.
Il lettore `expand_records` ricostruisce snapshot completi per i viewer.
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, List

from telemetry.logger import BinaryTelemetryLogger, iter_records

_SNAPSHOT_KEYS = (
    "agent_id",
    "name",
    "x",
    "y",
    "state",
    "target",
    "energy",
    "hunger",
    "money",
    "job",
    "skills",
    "thought",
)


class DeltaTelemetryLogger(BinaryTelemetryLogger):
    def __init__(self, path: str, metadata: dict, flush_every: int = 30, keyframe_every: int = 60):
        super().__init__(path, metadata, flush_every)
        self.keyframe_every = max(1, int(keyframe_every))
        self._prev: Dict[str, dict] = {}
        self.stats = {"keyframes": 0, "deltas": 0, "full_events": 0, "delta_events": 0}

    def log_tick(self, tick: int, sim_time: float, events: list[dict]):
        compacted: List[dict] = []
        is_key = (tick % self.keyframe_every == 0) or not self._prev
        if is_key:
            self.stats["keyframes"] += 1
        else:
            self.stats["deltas"] += 1
        for ev in events:
            if ev.get("type") != "snapshot":
                compacted.append(ev)
                continue
            aid = ev["agent_id"]
            if is_key or aid not in self._prev:
                compacted.append({**ev, "delta": False})
                self._prev[aid] = {k: ev.get(k) for k in _SNAPSHOT_KEYS}
                self.stats["full_events"] += 1
            else:
                prev = self._prev[aid]
                delta = {"type": "snapshot", "agent_id": aid, "delta": True, "tick": ev.get("tick", tick)}
                changed = False
                for k in _SNAPSHOT_KEYS:
                    if k == "agent_id":
                        continue
                    if prev.get(k) != ev.get(k):
                        delta[k] = ev.get(k)
                        changed = True
                if changed:
                    compacted.append(delta)
                    self.stats["delta_events"] += 1
                self._prev[aid] = {k: ev.get(k) for k in _SNAPSHOT_KEYS}
        super().log_tick(tick, sim_time, compacted)

    def compression_ratio(self) -> float:
        full = max(1, self.stats["full_events"])
        return (full + self.stats["delta_events"]) / full


def expand_records(path: str, tolerate_truncated: bool = False) -> Iterator[dict]:
    """Yield records with snapshot deltas espansi a snapshot completi."""
    state: Dict[str, dict] = {}
    for rec in iter_records(path, tolerate_truncated=tolerate_truncated):
        if rec.get("record") != "tick":
            yield rec
            continue
        events = []
        for ev in rec.get("events", []):
            if ev.get("type") != "snapshot":
                events.append(ev)
                continue
            aid = ev["agent_id"]
            if ev.get("delta"):
                cur = dict(state.get(aid, {"type": "snapshot", "agent_id": aid}))
                cur.update({k: v for k, v in ev.items() if k != "delta"})
                cur["type"] = "snapshot"
                cur["delta"] = False
                state[aid] = cur
                events.append(dict(cur))
            else:
                cur = {k: v for k, v in ev.items() if k != "delta"}
                cur["delta"] = False
                state[aid] = cur
                events.append(dict(cur))
        out = dict(rec)
        out["events"] = events
        yield out
