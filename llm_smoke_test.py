"""Smoke test manuale contro un endpoint di chat completion reale.

Esempio:
  python llm_smoke_test.py --api-base http://localhost:8000/v1 --model my-model
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile

from llm.http_transport import ChatCompletionHTTPTransport
from llm.router import CognitiveRouter


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--api-base", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--api-key-env", default="CIVITAS_LLM_API_KEY")
    a = p.parse_args()
    transport = ChatCompletionHTTPTransport(a.api_base, a.model, os.getenv(a.api_key_env))
    with tempfile.TemporaryDirectory() as d:
        r = CognitiveRouter(
            True, a.model, a.api_base, 30, 1, d + "/trace.jsonl", 42, transport=transport
        )
        decision = await r.decide(
            agent_id="smoke_agent",
            tick=0,
            event="smoke_test",
            choices=["continue", "stop"],
            system_prompt=(
                'Scegli solo tra le opzioni date e restituisci JSON valido: '
                '{"choice":"...","thought":"...","confidence":0.0}.'
            ),
            context={"purpose": "healthcheck"},
        )
        print(
            json.dumps(
                {"ok": True, "decision": decision.__dict__, "stats": r.stats},
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
