"""Modelli Issue per Paperclip-city — task board locale per agenti cognitivi."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

IssueStatus = Literal["todo", "in_progress", "done", "blocked"]
IssueKind = Literal["reflect", "career", "study", "social", "governance"]

COGNITIVE_KINDS: tuple[str, ...] = ("reflect", "career", "study", "social")
# "governance" NON e' qui: e' condizionale (solo se esistono proposte attive
# o l'agente puo' proporne una), non un issue fisso ogni giorno per tutti.

# Mappa kind board → evento router / tipo telemetria
KIND_TO_EVENT: dict[str, str] = {
    "reflect": "daily_reflection",
    "career": "career_choice",
    "study": "study_focus",
    "social": "social_stance",
    "governance": "governance_choice",
}


@dataclass
class Issue:
    id: str
    agent_id: str
    kind: str
    status: IssueStatus = "todo"
    tick: int = 0
    day: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Issue:
        return cls(
            id=str(raw["id"]),
            agent_id=str(raw["agent_id"]),
            kind=str(raw["kind"]),
            status=raw.get("status", "todo"),
            tick=int(raw.get("tick") or 0),
            day=int(raw.get("day") or 0),
            payload=dict(raw.get("payload") or {}),
            result=raw.get("result"),
        )
