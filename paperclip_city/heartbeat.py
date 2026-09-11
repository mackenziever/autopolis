"""Heartbeat Paperclip-city: coordina issue giornaliere e prefetch cognitivo opzionale."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from paperclip_city.models import KIND_TO_EVENT

if TYPE_CHECKING:
    from agents.state_machine import AgentFSM
    from config import SimConfig
    from llm.cognitive_worker import CognitiveWorker
    from paperclip_city.board import Board


async def run_heartbeat(
    board: Board,
    agents: List[AgentFSM],
    day: int,
    tick: int,
    *,
    cognitive_worker: Optional[CognitiveWorker] = None,
    cfg: Optional[SimConfig] = None,
    governance: Any = None,
) -> dict[str, Any]:
    """Un heartbeat: assicura issue giornaliere; opzionalmente enqueue worker LLM."""
    agent_ids = [a.r.agent_id for a in agents]
    created = board.create_daily_issues(agent_ids, day, tick)

    if governance is not None:
        open_proposals = governance.open_proposals()
        if open_proposals:
            deadline = max(p.closes_tick for p in open_proposals)
            created += board.create_governance_issue(
                agent_ids, day, tick, [p.proposal_id for p in open_proposals], deadline
            )

    enqueued = 0
    if cognitive_worker is not None and cfg is not None and cfg.llm_enabled:
        from llm.cognitive_worker import CognitiveJob

        for agent in agents:
            for kind, event in KIND_TO_EVENT.items():
                issue = board.find_issue(agent.r.agent_id, day, kind)
                if issue is None or issue.status != "todo":
                    continue
                choices = _choices_for_kind(kind)
                if not choices:
                    continue
                ok = cognitive_worker.submit_nowait(
                    CognitiveJob(
                        agent_id=agent.r.agent_id,
                        tick=tick,
                        event=event,
                        choices=choices,
                        system_prompt=agent.cog.prompt(),
                        context={"paperclip_issue_id": issue.id, "day": day},
                    )
                )
                if ok:
                    board.checkout(agent.r.agent_id, issue.id, tick)
                    enqueued += 1

    return {"day": day, "tick": tick, "created": created, "enqueued": enqueued}


def _choices_for_kind(kind: str) -> list[str]:
    if kind == "reflect":
        return ["consolidate_skills", "recover_energy", "seek_social", "push_study"]
    if kind == "career":
        return ["stay", "apply_layout_designer", "apply_motion_designer", "apply_ux_designer", "apply_webgl_developer"]
    if kind == "study":
        return ["layout_101", "motion_201", "interaction_202", "webgl_301"]
    if kind == "social":
        return ["network", "observe", "help", "rest"]
    if kind == "governance":
        return ["vote_yes", "vote_no", "vote_abstain", "skip_governance"]
    return []
