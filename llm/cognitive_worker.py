"""Worker cognitivo fuori dal hot-path del movimento.

Il tick continua a usare `CognitiveRouter.decide` per eventi rari. Questo worker
serve per batch offline / prefetch: mette in coda job e scrive sulla trace senza
bloccare il loop di movimento quando usato in fire-and-forget.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass
class CognitiveJob:
    agent_id: str
    tick: int
    event: str
    choices: List[str]
    system_prompt: str
    context: dict


class CognitiveWorker:
    def __init__(
        self,
        decide: Callable[..., Awaitable[Any]],
        *,
        maxsize: int = 256,
    ):
        self._decide = decide
        self.queue: asyncio.Queue[Optional[CognitiveJob]] = asyncio.Queue(maxsize=maxsize)
        self.stats = {"submitted": 0, "done": 0, "errors": 0, "dropped": 0}
        self._task: Optional[asyncio.Task] = None

    def start(self) -> "CognitiveWorker":
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
        return self

    async def stop(self) -> None:
        await self.queue.put(None)
        if self._task:
            await self._task
            self._task = None

    def submit_nowait(self, job: CognitiveJob) -> bool:
        try:
            self.queue.put_nowait(job)
            self.stats["submitted"] += 1
            return True
        except asyncio.QueueFull:
            self.stats["dropped"] += 1
            return False

    async def _loop(self) -> None:
        while True:
            job = await self.queue.get()
            if job is None:
                return
            try:
                await self._decide(
                    agent_id=job.agent_id,
                    tick=job.tick,
                    event=job.event,
                    choices=job.choices,
                    system_prompt=job.system_prompt,
                    context=job.context,
                )
                self.stats["done"] += 1
            except Exception:
                self.stats["errors"] += 1
