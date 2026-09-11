"""Kernel AGI-OS per agente: identità vivente sopra la FSM (no LLM nel movimento)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.models import AgentRuntime

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SOUL = _ROOT / "vault" / "SOUL.md"
# FreeLLM free-tier: keep AGI-OS soul excerpt small so boot_prompt stays cheap.
SOUL_EXCERPT_MAX = 1200


@lru_cache(maxsize=4)
def _load_soul_text(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        return (
            "Civitas AGI-OS: rispetta impegni, apprendi, condividi lesson in Alveare. "
            "Movimento deterministico; cognizione su eventi rari via FreeLLM."
        )
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "Civitas AGI-OS (soul unread)."
    # Cap for FreeLLM free-tier prompt budget (boot_prompt inject)
    if len(text) > SOUL_EXCERPT_MAX:
        return text[:SOUL_EXCERPT_MAX] + "\n…"
    return text


class AgiOsKernel:
    """Mini sistema operativo agentico legato a un AgentRuntime."""

    def __init__(
        self,
        runtime: AgentRuntime,
        *,
        soul_path: str | Path | None = None,
        improve=None,
        strategy: str = "",
        paperclip_board=None,
    ):
        self.r = runtime
        self.os_id = f"agi_os_{runtime.agent_id}"
        self.soul_path = str(soul_path or _DEFAULT_SOUL)
        self.improve = improve
        self._strategy_ref = strategy  # may be updated via set_strategy
        self.paperclip_board = paperclip_board
        self.boot_count = 0
        self.last_events: List[dict] = []

    def set_strategy(self, strategy: str) -> None:
        self._strategy_ref = strategy

    def bind_improve(self, improve) -> None:
        self.improve = improve

    def soul_excerpt(self) -> str:
        return _load_soul_text(self.soul_path)

    def boot_prompt(self, base_prompt: str) -> str:
        """Arricchisce il prompt cognitivo con blocco AGI-OS."""
        self.boot_count += 1
        p = self.r.persona
        focus = getattr(self.improve, "focus", "study") if self.improve else "study"
        lessons = []
        if self.improve is not None:
            lessons = list(getattr(self.improve, "lessons", []) or [])[-3:]
        lesson_txt = " | ".join(lessons) if lessons else "(nessuna lesson ancora)"
        block = (
            f"--- AGI-OS ---\n"
            f"os_id={self.os_id}\n"
            f"citizen={p.display_name} ({self.r.agent_id})\n"
            f"focus={focus}; job={self.r.job}; course={self.r.course_id()}\n"
            f"strategy={self._strategy_ref or '(boot)'}\n"
            f"recent_lessons={lesson_txt}\n"
            f"soul:\n{self.soul_excerpt()}\n"
            f"--- END AGI-OS ---"
        )
        return f"{base_prompt}\n\n{block}"

    def record_event(self, event: dict) -> None:
        self.last_events.append(event)
        if len(self.last_events) > 32:
            self.last_events = self.last_events[-32:]

    def heartbeat_state(self) -> Dict[str, Any]:
        focus = getattr(self.improve, "focus", None) if self.improve else None
        inbox: list = []
        if self.paperclip_board is not None:
            try:
                inbox = [
                    {"id": i.id, "kind": i.kind, "status": i.status}
                    for i in self.paperclip_board.list_inbox(self.r.agent_id)
                ]
            except Exception:
                inbox = []
        return {
            "os_id": self.os_id,
            "agent_id": self.r.agent_id,
            "name": self.r.persona.display_name,
            "job": self.r.job,
            "course": self.r.course_id(),
            "skills": list(self.r.skills),
            "focus": focus,
            "strategy": self._strategy_ref,
            "thought": self.r.last_thought,
            "energy": round(self.r.energy, 2),
            "hunger": round(self.r.hunger, 2),
            "money": round(self.r.money, 2),
            "state": str(self.r.state),
            "position": list(self.r.position),
            "paperclip_inbox": inbox,
            "boot_count": self.boot_count,
            "living": True,
        }
