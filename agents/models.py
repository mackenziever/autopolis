"""Tipi di dominio serializzabili. Nessun oggetto mutabile entra nei log."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import StrEnum
from typing import Any, Dict, List, Optional, Tuple
from config import Coord

class AgentState(StrEnum):
    IDLE = "IDLE"
    COMMUTING = "COMMUTING"
    WORKING = "WORKING"
    ATTENDING_CLASS = "ATTENDING_CLASS"
    EXPLORING = "EXPLORING"
    SOCIALIZING = "SOCIALIZING"
    EATING = "EATING"
    REST = "REST"

@dataclass(frozen=True)
class Persona:
    display_name: str
    age: int
    diligence: float
    sociability: float
    curiosity: float
    risk_tolerance: float
    preferred_course: str
    biography: str

@dataclass
class AgentRuntime:
    agent_id: str
    number: int
    persona: Persona
    position: Coord
    state: AgentState = AgentState.IDLE
    previous_state: AgentState = AgentState.IDLE
    target_poi: str = "Home"
    path: List[Coord] = field(default_factory=list)
    energy: float = 100.0
    hunger: float = 0.0
    money: float = 20.0
    job: str = "intern"
    skills: List[str] = field(default_factory=lambda: ["basic_literacy"])
    study_progress: Dict[str, int] = field(default_factory=dict)
    relationships: Dict[str, float] = field(default_factory=dict)
    last_thought: str = "Mi sto svegliando."
    exam_attempted_day: int = -1
    reflected_day: int = -1
    # Corso attivo mutabile (Persona.preferred_course resta fingerprint-stabile).
    active_course: str = ""
    career_decided_day: int = -1
    study_focused_day: int = -1
    social_decided_day: int = -1
    build_decided_day: int = -1
    room_decided_day: int = -1
    research_decided_day: int = -1
    governance_decided_day: int = -1

    def course_id(self) -> str:
        return self.active_course or self.persona.preferred_course

    def snapshot(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id, "name": self.persona.display_name,
            "x": self.position[0], "y": self.position[1], "state": str(self.state),
            "target": self.target_poi, "energy": round(self.energy, 3),
            "hunger": round(self.hunger, 3), "money": round(self.money, 3),
            "job": self.job, "skills": list(self.skills),
            "course": self.course_id(),
            "thought": self.last_thought,
        }
