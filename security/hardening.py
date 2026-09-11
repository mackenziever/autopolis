"""Hardening: rate limit, validazione input, secret masking."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Dict, Tuple


class RateLimitExceeded(RuntimeError):
    pass


class ValidationError(ValueError):
    pass


class TokenBucket:
    """Rate limiter token-bucket thread-safe a livello logico (single-process)."""

    def __init__(self, rate_per_s: float, capacity: float):
        self.rate = float(rate_per_s)
        self.capacity = float(capacity)
        self._tokens: Dict[str, float] = {}
        self._ts: Dict[str, float] = {}

    def allow(self, key: str, cost: float = 1.0) -> bool:
        now = time.monotonic()
        if key not in self._ts:
            self._ts[key] = now
            self._tokens[key] = self.capacity
        elapsed = max(0.0, now - self._ts[key])
        self._ts[key] = now
        self._tokens[key] = min(self.capacity, self._tokens[key] + elapsed * self.rate)
        if self._tokens[key] < cost:
            return False
        self._tokens[key] -= cost
        return True

    def require(self, key: str, cost: float = 1.0) -> None:
        if not self.allow(key, cost):
            raise RateLimitExceeded(f"rate limit exceeded for {key}")


class InputValidator:
    _AGENT = re.compile(r"^agent_\d{3,6}$|^[a-zA-Z][a-zA-Z0-9_\-]{0,63}$")
    _CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

    @classmethod
    def agent_id(cls, value: str) -> str:
        if not isinstance(value, str) or not cls._AGENT.match(value):
            raise ValidationError(f"agent_id non valido: {value!r}")
        return value

    @classmethod
    def path(cls, value: str, *, must_be_relative: bool = True) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("path vuoto")
        normalized = value.replace("\\", "/")
        p = Path(normalized)
        if must_be_relative:
            if p.is_absolute() or normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
                raise ValidationError("path assoluto non ammesso")
        if ".." in p.parts or "/../" in f"/{normalized}/":
            raise ValidationError("path traversal non ammesso")
        return normalized

    @classmethod
    def sanitize_prompt(cls, text: str, max_len: int = 8_000) -> str:
        if not isinstance(text, str):
            raise ValidationError("prompt non testuale")
        cleaned = cls._CTRL.sub("", text)
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len]
        return cleaned

    @classmethod
    def sanitize_context(cls, context: dict, max_keys: int = 64) -> dict:
        if not isinstance(context, dict):
            raise ValidationError("context non e' un oggetto")
        if len(context) > max_keys:
            raise ValidationError("context troppo grande")
        out = {}
        for k, v in list(context.items())[:max_keys]:
            key = str(k)[:64]
            if isinstance(v, str):
                out[key] = cls.sanitize_prompt(v, 2_000)
            elif isinstance(v, (int, float, bool)) or v is None:
                out[key] = v
            elif isinstance(v, list):
                out[key] = v[:32]
            elif isinstance(v, dict):
                out[key] = {str(sk)[:64]: sv for sk, sv in list(v.items())[:16]}
            else:
                out[key] = str(v)[:500]
        return out


class SecretManager:
    """Segreti solo da environment; masking per log/prompt."""

    def __init__(
        self,
        env_names: Tuple[str, ...] = (
            "CIVITAS_LLM_API_KEY",
            "CIVITAS_GATEWAY_TOKEN",
            "CIVITAS_REPLAY_HMAC_KEY",
            "CIVITAS_ZMQ_HMAC_KEY",
            "OPENAI_API_KEY",
            "SAKANA_API_KEY",
        ),
    ):
        self.env_names = env_names

    def require(self, name: str) -> str:
        value = self.get(name)
        if not value:
            raise ValidationError(f"secret richiesto assente: {name}")
        return value

    def get(self, name: str) -> str | None:
        return os.getenv(name) or None

    def mask(self, text: str) -> str:
        out = text
        for name in self.env_names:
            secret = os.getenv(name)
            if secret and secret in out:
                out = out.replace(secret, "***REDACTED***")
        return out
