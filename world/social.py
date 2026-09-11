"""Interazioni sociali emergenti da prossimita', con cooldown deterministico."""
from __future__ import annotations
import hashlib
from typing import Dict, List, Tuple
from agents.models import AgentRuntime, AgentState

class SocialSystem:
    def __init__(self, cooldown_ticks: int = 25):
        self.cooldown = cooldown_ticks; self.last: Dict[Tuple[str,str],int] = {}

    def process(self, tick: int, pairs: List[Tuple[str,str]], by_id: Dict[str,AgentRuntime]) -> List[dict]:
        events=[]
        for a_id,b_id in pairs:
            a,b=by_id[a_id],by_id[b_id]
            if a.state != AgentState.SOCIALIZING or b.state != AgentState.SOCIALIZING: continue
            key=(a_id,b_id)
            if tick-self.last.get(key,-10**9)<self.cooldown: continue
            raw=hashlib.sha256(f"{tick}:{a_id}:{b_id}".encode()).digest()
            delta=round((raw[0]/255-.35)*.12,3)
            a.relationships[b_id]=round(max(-1,min(1,a.relationships.get(b_id,0)+delta)),3)
            b.relationships[a_id]=round(max(-1,min(1,b.relationships.get(a_id,0)+delta)),3)
            self.last[key]=tick
            tone="positivo" if delta>=0 else "teso"
            place = "piazza"
            if a.target_poi == b.target_poi and a.target_poi not in ("Plaza", "Home", ""):
                place = a.target_poi
            events.append({"type":"conversation","tick":tick,"agents":[a_id,b_id],
                           "delta":delta,"poi": place,
                           "thought":f"Scambio {tone} a {place}."})
        return events
