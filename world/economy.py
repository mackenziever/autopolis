"""Mercato del lavoro deterministico: skill -> idoneita' -> assunzione nello stesso tick."""
from __future__ import annotations
from collections import Counter
from typing import Dict, List, Tuple
from config import JOBS
from agents.models import AgentRuntime

class LaborMarket:
    def __init__(self): self.hires_by_role = Counter()

    def best_eligible_job(self, agent: AgentRuntime) -> str:
        candidates = []
        for role, (skill, wage, slots) in JOBS.items():
            if skill in agent.skills and self.hires_by_role[role] < slots:
                candidates.append((wage, role))
        return max(candidates, default=(1.0,"intern"))[1]

    def hire_if_eligible(self, tick: int, agent: AgentRuntime):
        role = self.best_eligible_job(agent)
        return self.apply_job(tick, agent, role)

    def apply_job(self, tick: int, agent: AgentRuntime, role: str):
        """Applica un ruolo se idoneo (skill + slot). Usato da hire auto e da LLM career."""
        if role not in JOBS or role == "train_more":
            return None
        skill, _wage, slots = JOBS[role]
        if skill not in agent.skills and skill != "basic_literacy":
            return None
        if role != "intern" and self.hires_by_role[role] >= slots and agent.job != role:
            return None
        if role == agent.job:
            return None
        old = agent.job
        if old in self.hires_by_role and old != "intern":
            self.hires_by_role[old] -= 1
        agent.job = role
        if role != "intern":
            self.hires_by_role[role] += 1
        return {
            "type": "job_change",
            "tick": tick,
            "agent_id": agent.agent_id,
            "from": old,
            "to": role,
            "thought": f"Assunto come {role} nello stesso giorno.",
        }

    def wage(self, agent: AgentRuntime) -> float:
        return JOBS[agent.job][1]
