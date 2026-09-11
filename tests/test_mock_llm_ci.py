"""Mock endpoint di chat completion (stdlib) per CI senza pull GHCR FreeLLMAPI."""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from llm.http_transport import ChatCompletionHTTPTransport
from llm.router import CognitiveRouter


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(n)
        if self.path.endswith("/embeddings"):
            body = {
                "data": [{"embedding": [0.1] * 8 + [0.0] * 376, "index": 0}],
                "model": "mock-embed",
            }
        else:
            body = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "choice": "consolidate_skills",
                                    "thought": "mock ok",
                                    "confidence": 0.8,
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def test_mock_llm_compatible_router(tmp_path):
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}/v1"
        transport = ChatCompletionHTTPTransport(base, "mock-model", api_key="x")
        router = CognitiveRouter(
            True,
            "mock-model",
            base,
            5.0,
            2,
            str(tmp_path / "t.jsonl"),
            7,
            transport=transport,
        )

        async def _go():
            d = await router.decide(
                agent_id="agent_001",
                tick=1,
                event="daily_reflection",
                choices=["consolidate_skills", "recover_energy"],
                system_prompt="test",
                context={},
            )
            return d

        d = asyncio.run(_go())
        assert d.choice == "consolidate_skills"
        assert router.stats["live"] == 1
    finally:
        httpd.shutdown()
