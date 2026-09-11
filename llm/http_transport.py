"""Transport HTTP per endpoint di chat completion (standard di settore, formato
diffuso fra i provider), senza dipendenze — usabile per smoke/integration test."""
from __future__ import annotations

import asyncio
import json
import urllib.request


class ChatCompletionHTTPTransport:
    def __init__(
        self,
        api_base: str,
        model: str,
        api_key: str | None = None,
        max_tokens: int = 256,
        timeout_s: float = 20.0,
    ):
        self.url = api_base.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s

    def _sync(self, messages):
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": self.max_tokens,
                "response_format": {"type": "json_object"},
            }
        ).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            data = json.loads(r.read().decode())
        usage = data.get("usage") or {}
        return {
            "content": data["choices"][0]["message"]["content"],
            "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "output_tokens": int(usage.get("completion_tokens", 0) or 0),
        }

    async def __call__(self, *, messages, **_):
        return await asyncio.to_thread(self._sync, messages)
