"""Budget deterministici di richieste/token per agente, giorno e simulazione."""
from __future__ import annotations

from typing import Dict, Tuple


class TokenBudget:
    def __init__(
        self,
        *,
        requests_per_agent: int,
        input_per_agent: int,
        output_per_agent: int,
        global_requests: int,
        global_input: int,
        global_output: int,
    ):
        self.limits = {
            "agent_requests": requests_per_agent,
            "agent_input": input_per_agent,
            "agent_output": output_per_agent,
            "global_requests": global_requests,
            "global_input": global_input,
            "global_output": global_output,
        }
        self.agent: Dict[Tuple[int, str], dict] = {}
        self.global_day: Dict[int, dict] = {}

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # Stima conservativa provider-agnostic: circa 4 caratteri/token.
        return max(1, (len(text) + 3) // 4)

    def _a(self, day: int, agent_id: str) -> dict:
        return self.agent.setdefault(
            (day, agent_id), {"requests": 0, "input_tokens": 0, "output_tokens": 0}
        )

    def _g(self, day: int) -> dict:
        return self.global_day.setdefault(
            day, {"requests": 0, "input_tokens": 0, "output_tokens": 0}
        )

    def allow(
        self, day: int, agent_id: str, estimated_input: int, reserved_output: int
    ) -> tuple[bool, str]:
        a, g = self._a(day, agent_id), self._g(day)
        L = self.limits
        tests = [
            (a["requests"] + 1 <= L["agent_requests"], "agent_requests"),
            (a["input_tokens"] + estimated_input <= L["agent_input"], "agent_input_tokens"),
            (a["output_tokens"] + reserved_output <= L["agent_output"], "agent_output_tokens"),
            (g["requests"] + 1 <= L["global_requests"], "global_requests"),
            (g["input_tokens"] + estimated_input <= L["global_input"], "global_input_tokens"),
            (g["output_tokens"] + reserved_output <= L["global_output"], "global_output_tokens"),
        ]
        for ok, reason in tests:
            if not ok:
                return False, reason
        return True, "ok"

    def charge(self, day: int, agent_id: str, input_tokens: int, output_tokens: int) -> None:
        a, g = self._a(day, agent_id), self._g(day)
        for x in (a, g):
            x["requests"] += 1
            x["input_tokens"] += int(input_tokens)
            x["output_tokens"] += int(output_tokens)

    def snapshot(self) -> dict:
        return {
            "limits": dict(self.limits),
            "agent": [[day, aid, dict(v)] for (day, aid), v in sorted(self.agent.items())],
            "global_day": [[day, dict(v)] for day, v in sorted(self.global_day.items())],
        }

    def restore(self, data: dict | None) -> None:
        if not data:
            return
        self.agent = {(int(day), aid): dict(v) for day, aid, v in data.get("agent", [])}
        self.global_day = {int(day): dict(v) for day, v in data.get("global_day", [])}
