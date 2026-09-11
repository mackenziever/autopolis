"""Manifest operativo del run (sidecar JSON, non entra nel replay)."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any


def write_run_manifest(
    *,
    path: str,
    cfg_fingerprint: str,
    seed: int,
    agents: int,
    ticks_completed: int,
    log_path: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    log = Path(log_path)
    sha = hashlib.sha256(log.read_bytes()).hexdigest() if log.exists() else None
    manifest = {
        "schema": 1,
        "created_unix": time.time(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "fingerprint": cfg_fingerprint,
        "seed": seed,
        "agents": agents,
        "ticks_completed": ticks_completed,
        "log_path": str(log_path),
        "log_sha256": sha,
        "extra": extra or {},
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
