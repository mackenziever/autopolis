"""Buffer upsert Alveare: visibilità solo a fine tick, ordine deterministico."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from knowledge.client import AlveareClient


@dataclass(frozen=True)
class PendingUpsert:
    agent_id: str
    tick: int
    text: str
    source: str
    tags: tuple[str, ...]


class AlveareBatchBuffer:
    """Raccoglie upsert durante il tick; flush ordinato per agent_id."""

    def __init__(self, client: AlveareClient | None, *, frozen: bool = False):
        self.client = client
        self.frozen = frozen
        self._pending: List[PendingUpsert] = []

    def enqueue(
        self,
        *,
        agent_id: str,
        tick: int,
        text: str,
        source: str = "agent",
        tags: Optional[List[str]] = None,
    ) -> None:
        if self.frozen or not self.client or not (text or "").strip():
            return
        self._pending.append(
            PendingUpsert(
                agent_id=agent_id,
                tick=tick,
                text=text.strip(),
                source=source,
                tags=tuple(tags or ()),
            )
        )

    def flush(self) -> dict:
        if self.frozen or not self.client or not self._pending:
            n = len(self._pending)
            self._pending.clear()
            return {"flushed": 0, "skipped": n, "frozen": self.frozen}
        ordered = sorted(self._pending, key=lambda p: (p.tick, p.agent_id, p.text))
        self._pending.clear()
        ok = 0
        for item in ordered:
            res = self.client.upsert(
                item.text,
                source=item.source,
                tags=list(item.tags),
                agent_id=item.agent_id,
                tick=item.tick,
            )
            if res.get("ok", True) and "error" not in res:
                ok += 1
        return {"flushed": ok, "total": len(ordered), "frozen": False}
