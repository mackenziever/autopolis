#!/usr/bin/env python3
"""Genera SBOM CycloneDX-like minimale in sbom.json."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    components = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(p in path.parts for p in (".venv", "__pycache__", "audit", ".git")):
            continue
        rel = path.relative_to(ROOT).as_posix()
        components.append(
            {
                "type": "file",
                "name": rel,
                "version": "0.1.0",
                "hashes": [{"alg": "SHA-256", "content": _hash_file(path)}],
            }
        )
    req = ROOT / "requirements.txt"
    if req.exists():
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            components.append({"type": "library", "name": line, "version": "range"})
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "civitas-core",
                "version": "0.1.0",
            },
            "tools": [{"name": "generate_sbom.py", "version": "0.1.0"}],
            "properties": [
                {"name": "python", "value": sys.version.split()[0]},
                {"name": "platform", "value": platform.platform()},
            ],
        },
        "components": components,
    }
    out = ROOT / "sbom.json"
    out.write_text(json.dumps(bom, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(components)} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
