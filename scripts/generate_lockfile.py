#!/usr/bin/env python3
"""Genera un lockfile piattaforma-specifico da requirements.txt / ambiente."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out = ROOT / "requirements.lock.json"
    freeze = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    packages = []
    for line in freeze.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            name, ver = line.split("==", 1)
            packages.append({"name": name, "version": ver})
        else:
            packages.append({"name": line, "version": None})
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(packages)} packages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
