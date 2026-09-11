"""Collector metriche Prometheus-compatible, zero dipendenze obbligatorie."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, List, Tuple


class MetricsCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._started = time.time()

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, **labels) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, value: float, **labels) -> None:
        key = self._key(name, labels)
        with self._lock:
            bucket = self._histograms[key]
            bucket.append(float(value))
            if len(bucket) > 10_000:
                del bucket[:5_000]

    @staticmethod
    def _key(name: str, labels: dict) -> str:
        if not labels:
            return name
        parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{parts}}}"

    def render_prometheus(self) -> str:
        lines: List[str] = [
            "# HELP civitas_uptime_seconds Process uptime",
            "# TYPE civitas_uptime_seconds gauge",
            f"civitas_uptime_seconds {time.time() - self._started:.3f}",
        ]
        with self._lock:
            for key, val in sorted(self._counters.items()):
                base = key.split("{", 1)[0]
                lines.append(f"# TYPE {base} counter")
                lines.append(f"{key} {val}")
            for key, val in sorted(self._gauges.items()):
                base = key.split("{", 1)[0]
                lines.append(f"# TYPE {base} gauge")
                lines.append(f"{key} {val}")
            for key, samples in sorted(self._histograms.items()):
                if not samples:
                    continue
                ordered = sorted(samples)
                n = len(ordered)
                mean = sum(ordered) / n
                p95 = ordered[min(n - 1, int(n * 0.95))]
                if "{" in key:
                    prefix, rest = key.split("{", 1)
                    lab = rest[:-1]
                    lines.append(f"# TYPE {prefix} summary")
                    lines.append(f"{prefix}_count{{{lab}}} {n}")
                    lines.append(f"{prefix}_mean{{{lab}}} {mean}")
                    lines.append(f"{prefix}_p95{{{lab}}} {p95}")
                else:
                    lines.append(f"# TYPE {key} summary")
                    lines.append(f"{key}_count {n}")
                    lines.append(f"{key}_mean {mean}")
                    lines.append(f"{key}_p95 {p95}")
        return "\n".join(lines) + "\n"

    def get_counter(self, name: str, **labels) -> float:
        key = self._key(name, labels)
        with self._lock:
            return self._counters.get(key, 0.0)

    def summary(self, name: str, **labels) -> dict:
        """Riassunto JSON-friendly di un histogram, per /health (oltre al
        formato Prometheus di render_prometheus()). count=0 se nessun sample."""
        key = self._key(name, labels)
        with self._lock:
            samples = list(self._histograms.get(key, ()))
        if not samples:
            return {"count": 0, "mean": 0.0, "p95": 0.0, "last": 0.0}
        ordered = sorted(samples)
        n = len(ordered)
        return {
            "count": n,
            "mean": sum(ordered) / n,
            "p95": ordered[min(n - 1, int(n * 0.95))],
            "last": samples[-1],
        }

    def health(self) -> dict:
        with self._lock:
            return {
                "ok": True,
                "uptime_s": round(time.time() - self._started, 3),
                "counters": len(self._counters),
                "gauges": len(self._gauges),
                "histograms": len(self._histograms),
            }


GLOBAL_COLLECTOR = MetricsCollector()
