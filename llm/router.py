"""Router cognitivo: mock/live compatibile con il formato chat-completion standard, budget, trace e fallback.

Il transport e' iniettabile nei test. In produzione il default usa LiteLLM.
Il tick engine non usa questo router per il movimento ordinario.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import asdict
from typing import Awaitable, Callable, List

from llm.budget import TokenBudget
from llm.schemas import Decision
from security.hardening import InputValidator, SecretManager
from security.pii import PIISanitizer


class LLMTrace:
    def __init__(self, path: str):
        self.path, self.cache = path, {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        r = json.loads(line)
                        self.cache[r["request_id"]] = r["response"]

    def get(self, rid):
        return self.cache.get(rid)

    def put(self, rid, request, response):
        if rid in self.cache:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        rec = {"request_id": rid, "request": request, "response": response}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.cache[rid] = response

    def _write_trace(self, req_id: str, response: dict):
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {"request_id": req_id, "response": response}, ensure_ascii=False
                    )
                    + "\n"
                )
                f.flush()
            self.cache[req_id] = response


class CognitiveRouter:
    def __init__(
        self,
        enabled: bool,
        model: str,
        api_base: str,
        timeout_s: float,
        max_concurrency: int,
        trace_path: str,
        seed: int,
        *,
        day_length: int = 600,
        max_output_tokens: int = 256,
        api_key_env: str = "CIVITAS_LLM_API_KEY",
        requests_per_agent: int = 8,
        input_per_agent: int = 12_000,
        output_per_agent: int = 3_000,
        global_requests: int = 400,
        global_input: int = 600_000,
        global_output: int = 150_000,
        transport: Callable[..., Awaitable[dict]] | None = None,
    ):
        self.enabled, self.model, self.api_base = enabled, model, api_base
        self.timeout_s, self.seed, self.day_length = timeout_s, seed, day_length
        self.max_output_tokens, self.api_key_env = max_output_tokens, api_key_env
        self.sem = asyncio.Semaphore(max_concurrency)
        self.trace = LLMTrace(trace_path)
        self.transport = transport
        self.secrets = SecretManager((api_key_env,))
        self.budget = TokenBudget(
            requests_per_agent=requests_per_agent,
            input_per_agent=input_per_agent,
            output_per_agent=output_per_agent,
            global_requests=global_requests,
            global_input=global_input,
            global_output=global_output,
        )
        self.stats = {
            "live": 0,
            "replay": 0,
            "fallback": 0,
            "errors": 0,
            "budget_denied": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            # Observed only on live cognitive transport calls (not movement hot path).
            "last_latency_ms": 0.0,
            # Decisioni con escalate=False: Tier 1 saltato deliberatamente (agents/escalation.py).
            "tier0_skipped_escalation": 0,
            # Circuit breaker (consiglio esterno, 2026-09-11, "3. Circuit
            # breaker + fallback semantico"): freellmapi e' un'immagine Docker
            # di terze parti (free-tier, rate limit/timeout aggressivi) che non
            # possiamo modificare — la resilienza va sul lato client, qui.
            "circuit_breaker_trips": 0,
            "circuit_breaker_skipped": 0,
            "retries": 0,
        }
        # Stato del breaker: dopo CB_FAILURE_THRESHOLD fallimenti consecutivi
        # (post-retry), si apre per CB_OPEN_SECONDS — le richieste vengono
        # servite subito dal fallback deterministico invece di attendere un
        # timeout su un provider gia' noto instabile in questa finestra.
        self._cb_failures = 0
        self._cb_open_until = 0.0
        self.CB_FAILURE_THRESHOLD = 5
        self.CB_OPEN_SECONDS = 30.0
        self.CB_MAX_RETRIES = 2

    def stats_summary(self) -> dict:
        """Metriche derivate per /health (consiglio esterno, 2026-09-11,
        "5. Telemetry end-to-end"): tassi invece dei soli contatori grezzi,
        cosi' una degradazione del free-tier (freellmapi) si vede a colpo
        d'occhio senza dover fare i conti a mano sui contatori di self.stats."""
        s = self.stats
        decided = s["live"] + s["replay"] + s["fallback"]
        attempted = s["live"] + s["errors"]
        return {
            "llm_cache_hit_rate": round(s["replay"] / decided, 4) if decided else 0.0,
            "llm_proxy_error_rate": round(s["errors"] / attempted, 4) if attempted else 0.0,
            "circuit_breaker_open": time.time() < self._cb_open_until,
        }

    def _id(self, payload):
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    @staticmethod
    def _strip_fence(content: str) -> str:
        """Alcuni backend (es. llama.cpp con questo modello) avvolgono il JSON
        in un fence markdown ```json ... ``` anche con response_format json_object.
        Rimuove il fence se presente; altrimenti ritorna il testo invariato."""
        t = content.strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[1] if "\n" in t else t[3:]
            if t.rstrip().endswith("```"):
                t = t.rstrip()[:-3]
        return t.strip()

    def _fallback(self, rid, choices, event, reason="offline"):
        idx = (
            int(hashlib.sha256(f"{self.seed}:{rid}".encode()).hexdigest()[:8], 16)
            % len(choices)
        )
        return {
            "choice": choices[idx],
            "thought": f"Fallback deterministico per {event} ({reason}).",
            "confidence": 0.5,
            "source": "fallback",
        }

    async def _litellm_transport(self, *, messages, **kwargs):
        from litellm import acompletion

        # Custom compatibile con il formato chat-completion standard hosts (Hermes/llama.cpp/FreeLLM) need a provider prefix.
        model = self.model
        if self.api_base and "/" not in model.split(":", 1)[0]:
            model = f"openai/{model}"

        raw = await acompletion(
            model=model,
            api_base=self.api_base,
            api_key=os.getenv(self.api_key_env) or "local",
            temperature=0,
            seed=self.seed,
            max_tokens=self.max_output_tokens,
            response_format={"type": "json_object"},
            messages=messages,
        )
        usage = getattr(raw, "usage", None)
        content = raw.choices[0].message.content
        return {
            "content": content,
            "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        }

    async def healthcheck(self) -> dict:
        if not self.enabled:
            return {"ok": True, "mode": "disabled"}
        return {
            "ok": bool(self.api_base),
            "mode": "live",
            "api_base": self.api_base,
            "model": self.model,
        }

    async def decide(
        self,
        *,
        agent_id: str,
        tick: int,
        event: str,
        choices: List[str],
        system_prompt: str,
        context: dict,
        escalate: bool = True,
    ) -> Decision:
        """`escalate=False`: salta il tentativo di chiamata LLM live per QUESTA
        decisione (usa subito il fallback deterministico, Tier 0), anche se
        `self.enabled`. Il default True preserva il comportamento di sempre
        per ogni chiamante che non passa questo parametro esplicitamente —
        vedi agents/escalation.py per il gate a isteresi che lo calcola.
        Cache/replay restano intatti: un rid gia' registrato viene sempre
        riletto dal trace, a prescindere da `escalate`."""
        agent_id = InputValidator.agent_id(agent_id)
        system_prompt = InputValidator.sanitize_prompt(system_prompt)
        context = InputValidator.sanitize_context(context)
        system_prompt = PIISanitizer.sanitize_text(self.secrets.mask(system_prompt), max_len=8_000)
        context = PIISanitizer.sanitize_obj(context)
        payload = {
            "agent_id": agent_id,
            "tick": tick,
            "event": event,
            "choices": choices,
            "system_prompt": system_prompt,
            "context": context,
            "model": self.model,
        }
        rid = self._id(payload)
        recorded = self.trace.get(rid)
        if recorded is not None:
            self.stats["replay"] += 1
            return Decision.parse(recorded, choices, rid=rid)
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {"event": event, "choices": choices, "context": context},
                    ensure_ascii=False,
                ),
            },
        ]
        prompt = json.dumps(messages, ensure_ascii=False)
        estimated = self.budget.estimate_tokens(prompt)
        day = tick // self.day_length
        allowed, reason = self.budget.allow(day, agent_id, estimated, self.max_output_tokens)
        response = None
        if not allowed:
            self.stats["budget_denied"] += 1
            response = self._fallback(rid, choices, event, "budget:" + reason)
        elif not escalate:
            self.stats["tier0_skipped_escalation"] += 1
            response = self._fallback(rid, choices, event, "no_escalation")
        elif self.enabled and time.time() < self._cb_open_until:
            # Breaker aperto: il provider free-tier ha gia' fallito
            # ripetutamente in questa finestra, non ha senso attendere un
            # altro timeout — fallback immediato, come un evento raro deve
            # degradare gracefully invece di bloccare il tick dell'agente.
            self.stats["circuit_breaker_skipped"] += 1
            response = self._fallback(rid, choices, event, "circuit_open")
        elif self.enabled:
            for attempt in range(self.CB_MAX_RETRIES + 1):
                try:
                    async with self.sem:
                        fn = self.transport or self._litellm_transport
                        t0 = time.perf_counter()
                        try:
                            result = await asyncio.wait_for(
                                fn(
                                    messages=messages,
                                    agent_id=agent_id,
                                    tick=tick,
                                    event=event,
                                ),
                                timeout=self.timeout_s,
                            )
                        finally:
                            # Cheap observation: only runs on cognitive live calls.
                            self.stats["last_latency_ms"] = round(
                                (time.perf_counter() - t0) * 1000.0, 3
                            )
                    parsed = (
                        json.loads(self._strip_fence(result["content"]))
                        if isinstance(result.get("content"), str)
                        else result["content"]
                    )
                    response = asdict(Decision.parse(parsed, choices, source="live", rid=rid))
                    inp = int(result.get("input_tokens") or estimated)
                    out = int(
                        result.get("output_tokens")
                        or self.budget.estimate_tokens(result.get("content", ""))
                    )
                    self.budget.charge(day, agent_id, inp, out)
                    self.stats["live"] += 1
                    self.stats["input_tokens"] += inp
                    self.stats["output_tokens"] += out
                    self._cb_failures = 0
                    break
                except Exception:
                    if attempt < self.CB_MAX_RETRIES:
                        self.stats["retries"] += 1
                        await asyncio.sleep(0.3 * (2**attempt))
                        continue
                    self.stats["errors"] += 1
                    self._cb_failures += 1
                    if self._cb_failures >= self.CB_FAILURE_THRESHOLD:
                        self._cb_open_until = time.time() + self.CB_OPEN_SECONDS
                        self._cb_failures = 0
                        self.stats["circuit_breaker_trips"] += 1
        if response is None:
            response = self._fallback(
                rid, choices, event, "error" if self.enabled else "offline"
            )
            self.stats["fallback"] += 1
        if isinstance(response, dict) and "thought" in response:
            response["thought"] = PIISanitizer.sanitize_text(str(response["thought"]))
        self.trace.put(rid, payload, response)
        return Decision.parse(response, choices, rid=rid)
