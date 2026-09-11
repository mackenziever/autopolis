"""Applica blueprint JSON proposti da un consulente esterno (testo/log) → data/city_blueprints/.

Usage:
  python scripts/apply_external_blueprint.py
  python scripts/apply_external_blueprint.py --from path/to/proposal.log
  python scripts/apply_external_blueprint.py --text-file path.md --out-name custom_name
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from world.city_growth import parse_blueprints_from_text, validate_blueprint  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Validate+save externally-proposed city blueprints")
    p.add_argument(
        "--from",
        dest="src",
        required=True,
        help="path to the text/log file containing proposed blueprints",
    )
    p.add_argument("--text-file", help="Alternate markdown/text source")
    p.add_argument("--out-dir", default=str(ROOT / "data" / "city_blueprints"))
    p.add_argument("--out-name", default="")
    args = p.parse_args()

    src = Path(args.text_file) if args.text_file else Path(args.src)
    if not src.is_file():
        print(f"[fail] missing source {src}", file=sys.stderr)
        return 1
    text = src.read_text(encoding="utf-8", errors="replace")
    items = parse_blueprints_from_text(text)
    if not items:
        print("[fail] no valid blueprints parsed", file=sys.stderr)
        return 1

    valid = []
    for item in items:
        ok, reason = validate_blueprint(item)
        if ok:
            valid.append(item)
        else:
            print(f"[skip] {item.get('id')}: {reason}")

    if not valid:
        print("[fail] none valid", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = args.out_name or f"external_blueprint_{stamp}"
    out = out_dir / f"{name}.json"
    payload = {
        "source": str(src),
        "created_utc": stamp,
        "blueprints": valid,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ok] wrote {out} blueprints={len(valid)}")
    for b in valid:
        print(f"  - {b['id']} -> {b['poi']} @ {b['xy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
