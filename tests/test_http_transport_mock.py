"""Integration test: CognitiveRouter + chat-completion mock HTTP server."""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from llm.http_transport import ChatCompletionHTTPTransport
from llm.router import CognitiveRouter


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode())
        assert self.path.endswith("/chat/completions")
        assert body["model"]
        assert body["messages"]
        content = json.dumps(
            {"choice": "continue", "thought": "HTTP mock ok.", "confidence": 0.88}
        )
        payload = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
        }
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_):
        return


def test_chat_completion_http_mock_server(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}/v1"
        transport = ChatCompletionHTTPTransport(base, "mock-model", api_key="test-key")
        router = CognitiveRouter(
            True,
            "mock-model",
            base,
            5,
            1,
            str(tmp_path / "trace.jsonl"),
            7,
            transport=transport,
        )
        decision = asyncio.run(
            router.decide(
                agent_id="agent_000",
                tick=0,
                event="smoke",
                choices=["continue", "stop"],
                system_prompt="JSON",
                context={},
            )
        )
        assert decision.choice == "continue"
        assert router.stats["live"] == 1
        assert router.stats["input_tokens"] == 11
        assert router.stats["output_tokens"] == 5
    finally:
        server.shutdown()
