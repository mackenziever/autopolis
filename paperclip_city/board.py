"""Board store Paperclip-city: append JSONL + indice in-memory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from paperclip_city.models import COGNITIVE_KINDS, Issue


def make_issue_id(seed: int, agent_id: str, day: int, kind: str) -> str:
    """ID deterministico: seed + agent + day + kind."""
    raw = f"{seed}:{agent_id}:{day}:{kind}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class Board:
    def __init__(self, data_dir: str | Path, seed: int):
        self.seed = seed
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "issues.jsonl"
        self.issues: Dict[str, Issue] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                issue = Issue.from_dict(json.loads(line))
                self.issues[issue.id] = issue

    def _persist(self, issue: Issue) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(issue.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()

    def create_daily_issues(
        self, agent_ids: List[str], day: int, tick: int = 0
    ) -> int:
        """Crea issue giornaliere per ogni agente/kind. Idempotente."""
        created = 0
        for agent_id in sorted(agent_ids):
            for kind in COGNITIVE_KINDS:
                iid = make_issue_id(self.seed, agent_id, day, kind)
                if iid in self.issues:
                    continue
                issue = Issue(
                    id=iid,
                    agent_id=agent_id,
                    kind=kind,
                    status="todo",
                    tick=tick,
                    day=day,
                    payload={"day": day, "kind": kind},
                )
                self.issues[iid] = issue
                self._persist(issue)
                created += 1
        return created

    def create_governance_issue(
        self,
        agent_ids: List[str],
        day: int,
        tick: int,
        proposal_ids: List[str],
        deadline: int,
    ) -> int:
        """Un solo issue 'governance' per agente/giorno (non uno per proposta)."""
        created = 0
        for agent_id in sorted(agent_ids):
            iid = make_issue_id(self.seed, agent_id, day, "governance")
            if iid in self.issues:
                continue
            issue = Issue(
                id=iid,
                agent_id=agent_id,
                kind="governance",
                status="todo",
                tick=tick,
                day=day,
                payload={"proposal_ids": list(proposal_ids), "deadline": deadline},
            )
            self.issues[iid] = issue
            self._persist(issue)
            created += 1
        return created

    def checkout(self, agent_id: str, issue_id: str, tick: int) -> Optional[Issue]:
        issue = self.issues.get(issue_id)
        if issue is None or issue.agent_id != agent_id:
            return None
        if issue.status != "todo":
            return issue
        issue.status = "in_progress"
        issue.tick = tick
        self._persist(issue)
        return issue

    def complete(self, issue_id: str, result: str, tick: int) -> Optional[Issue]:
        issue = self.issues.get(issue_id)
        if issue is None:
            return None
        if issue.status == "done":
            return issue
        issue.status = "done"
        issue.result = (result or "")[:500] or None
        issue.tick = tick
        self._persist(issue)
        return issue

    def list_inbox(self, agent_id: str, status: Optional[str] = None) -> List[Issue]:
        items = [i for i in self.issues.values() if i.agent_id == agent_id]
        if status is not None:
            items = [i for i in items if i.status == status]
        return sorted(items, key=lambda x: (x.day, x.kind, x.id))

    def find_issue(self, agent_id: str, day: int, kind: str) -> Optional[Issue]:
        iid = make_issue_id(self.seed, agent_id, day, kind)
        return self.issues.get(iid)

    def stats(self) -> dict[str, int]:
        open_n = sum(
            1 for i in self.issues.values() if i.status in ("todo", "in_progress", "blocked")
        )
        done_n = sum(1 for i in self.issues.values() if i.status == "done")
        return {"paperclip_open": open_n, "paperclip_done": done_n, "paperclip_total": len(self.issues)}
