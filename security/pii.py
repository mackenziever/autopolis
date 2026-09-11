"""Sanitizzazione PII / dati personali da pensieri e prompt."""
from __future__ import annotations

import re
from typing import Any


_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_CF_IT = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.I)


class PIISanitizer:
    """Redazione deterministica: stessi input → stessi output mascherati."""

    @classmethod
    def sanitize_text(cls, text: str, *, max_len: int = 400) -> str:
        if not isinstance(text, str):
            return ""
        out = text
        out = _EMAIL.sub("[REDACTED_EMAIL]", out)
        out = _IBAN.sub("[REDACTED_IBAN]", out)
        out = _CARD.sub("[REDACTED_CARD]", out)
        out = _CF_IT.sub("[REDACTED_CF]", out)
        out = _PHONE.sub("[REDACTED_PHONE]", out)
        return out[:max_len]

    @classmethod
    def sanitize_obj(cls, obj: Any) -> Any:
        if isinstance(obj, str):
            return cls.sanitize_text(obj, max_len=8_000)
        if isinstance(obj, list):
            return [cls.sanitize_obj(x) for x in obj[:64]]
        if isinstance(obj, dict):
            return {str(k)[:64]: cls.sanitize_obj(v) for k, v in list(obj.items())[:64]}
        return obj
