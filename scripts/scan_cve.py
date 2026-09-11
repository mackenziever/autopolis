#!/usr/bin/env python3
"""Scansione CVE delle dipendenze installate via pip-audit (se disponibile)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out = ROOT / "audit" / "runtime" / "cve_scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-f", "json"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
        )
    except Exception as exc:
        payload = {"ok": False, "error": str(exc), "tool": "pip_audit"}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload))
        return 0  # non blocca se tool assente in locale
    try:
        data = json.loads(p.stdout) if p.stdout.strip() else {"raw": p.stdout}
    except json.JSONDecodeError:
        data = {"raw": p.stdout, "stderr": p.stderr}
    payload = {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stderr": p.stderr,
        "result": data,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"ok": payload["ok"], "returncode": p.returncode}))
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
