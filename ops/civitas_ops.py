#!/usr/bin/env python3
"""Bridge ops Civitas invocabile da CLI/automazione esterna.

Uscita: JSON su stdout. Non entra mai nel tick engine.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PY = sys.executable


def _run(cmd: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "cmd": cmd,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }


def cmd_run(args: argparse.Namespace) -> dict[str, Any]:
    cmd = [
        PY,
        "main.py",
        "--agents",
        str(args.agents),
        "--ticks",
        str(args.ticks),
        "--seed",
        str(args.seed),
        "--hz",
        str(args.hz),
        "--log",
        args.log,
    ]
    if args.fast:
        cmd.append("--fast")
    if args.llm:
        cmd.append("--llm")
    if args.metrics:
        cmd.extend(["--metrics", "--metrics-port", str(args.metrics_port)])
    if args.spatial_hash:
        cmd.append("--spatial-hash")
    if args.delta_log:
        cmd.extend(["--delta-log", "--keyframe-every", str(args.keyframe_every)])
    if args.checkpoint_every:
        cmd.extend(
            [
                "--checkpoint",
                args.checkpoint,
                "--checkpoint-every",
                str(args.checkpoint_every),
            ]
        )
    if args.resume:
        cmd.extend(["--resume", args.resume])
    result = _run(cmd)
    result["log"] = args.log
    return result


def cmd_audit(_: argparse.Namespace) -> dict[str, Any]:
    return _run([PY, "run_audit.py"])


def cmd_inspect(args: argparse.Namespace) -> dict[str, Any]:
    return _run([PY, "inspect_replay.py", args.log])


def cmd_determinism(args: argparse.Namespace) -> dict[str, Any]:
    return _run([PY, "check_determinism.py", args.a, args.b])


def cmd_smoke_llm(args: argparse.Namespace) -> dict[str, Any]:
    cmd = [PY, "llm_smoke_test.py", "--api-base", args.api_base, "--model", args.model]
    return _run(cmd)


def cmd_alveare_query(args: argparse.Namespace) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from knowledge.client import AlveareClient

    client = AlveareClient(args.url)
    hits = client.query(args.text, k=args.k)
    return {"ok": True, "hits": hits, "url": args.url}


def cmd_alveare_ingest(args: argparse.Namespace) -> dict[str, Any]:
    cmd = [
        PY,
        "scripts/alveare_ingest_vault.py",
        "--vault",
        args.vault,
    ]
    if args.url:
        cmd.extend(["--url", args.url])
    if args.limit_files:
        cmd.extend(["--limit-files", str(args.limit_files)])
    return _run(cmd)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Civitas ops bridge")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Esegue main.py")
    run.add_argument("--agents", type=int, default=50)
    run.add_argument("--ticks", type=int, default=300)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--hz", type=int, default=15)
    run.add_argument("--log", default="data/ops_sim.msgpack")
    run.add_argument("--fast", action="store_true", default=True)
    run.add_argument("--no-fast", action="store_false", dest="fast")
    run.add_argument("--llm", action="store_true")
    run.add_argument("--metrics", action="store_true")
    run.add_argument("--metrics-port", type=int, default=0)
    run.add_argument("--spatial-hash", action="store_true")
    run.add_argument("--delta-log", action="store_true")
    run.add_argument("--keyframe-every", type=int, default=60)
    run.add_argument("--checkpoint", default="data/ops.checkpoint.msgpack")
    run.add_argument("--checkpoint-every", type=int, default=0)
    run.add_argument("--resume", default=None)
    run.set_defaults(func=cmd_run)

    audit = sub.add_parser("audit", help="Esegue run_audit.py")
    audit.set_defaults(func=cmd_audit)

    insp = sub.add_parser("inspect", help="Ispeziona un replay")
    insp.add_argument("--log", default="data/ops_sim.msgpack")
    insp.set_defaults(func=cmd_inspect)

    det = sub.add_parser("determinism", help="Confronta due replay")
    det.add_argument("--a", required=True)
    det.add_argument("--b", required=True)
    det.set_defaults(func=cmd_determinism)

    smoke = sub.add_parser("smoke-llm", help="Smoke compatibile con il formato chat-completion standard")
    smoke.add_argument("--api-base", default="http://localhost:8081/v1")
    smoke.add_argument("--model", default="qwable-9b")
    smoke.set_defaults(func=cmd_smoke_llm)

    aq = sub.add_parser("alveare-query", help="Query RAG Alveare")
    aq.add_argument("--url", default="http://127.0.0.1:9200")
    aq.add_argument("--text", required=True)
    aq.add_argument("--k", type=int, default=4)
    aq.set_defaults(func=cmd_alveare_query)

    ai = sub.add_parser("alveare-ingest", help="Ingest vault → Alveare")
    ai.add_argument("--vault", default=r"D:\AETHER-VAULT")
    ai.add_argument("--url", default="http://127.0.0.1:9200")
    ai.add_argument("--limit-files", type=int, default=None)
    ai.set_defaults(func=cmd_alveare_ingest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
