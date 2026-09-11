"""OpenTelemetry-lite: export JSONL senza dipendenze obbligatorie.

Se `opentelemetry-api` e' installato, usa un tracer reale; altrimenti scrive
span JSON in `data/otel_spans.jsonl`.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class OTelBridge:
    def __init__(self, path: str = "data/otel_spans.jsonl", enabled: bool = True):
        self.enabled = enabled
        self.path = path
        self._otel = None
        if enabled:
            try:
                from opentelemetry import trace  # type: ignore

                self._otel = trace.get_tracer("civitas")
            except Exception:
                self._otel = None

    @contextmanager
    def span(self, name: str, **attrs) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        if self._otel is not None:
            with self._otel.start_as_current_span(name) as sp:
                for k, v in attrs.items():
                    try:
                        sp.set_attribute(k, v)
                    except Exception:
                        pass
                yield
            return
        start = time.time()
        sid = uuid.uuid4().hex
        try:
            yield
            status = "ok"
        except Exception as exc:
            status = f"error:{type(exc).__name__}"
            raise
        finally:
            rec = {
                "span_id": sid,
                "name": name,
                "start": start,
                "end": time.time(),
                "status": status,
                "attrs": attrs,
            }
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


GLOBAL_OTEL = OTelBridge(enabled=os.getenv("CIVITAS_OTEL", "0") == "1")
