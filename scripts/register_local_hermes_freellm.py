"""Registra Hermes/llama.cpp locale come provider FreeLLM (custom/ollama).

Non stampa secret. Uso:
  set FREELLM_PASSWORD=...
  python scripts/register_local_hermes_freellm.py
  python scripts/register_local_hermes_freellm.py --base-url http://host.docker.internal:8081/v1

Exit codes:
  0  — registered OK, OR clean skip when Hermes/local (:8081) is unreachable
       (FreeLLM free-tier remains usable without local Hermes)
  1  — missing FREELLM_PASSWORD, FreeLLM login failure, or key registration failure
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def http_json(
    method: str,
    url: str,
    token: str | None = None,
    body: dict | None = None,
    *,
    timeout: float = 20,
):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"raw": raw[:300]}
        return e.code, parsed
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": str(exc), "unreachable": True}
    except Exception as exc:
        return 0, {"error": str(exc), "unreachable": True}


def hermes_up(url: str) -> bool:
    """True if the local chat-completion endpoint answers; never raises.

    Uses a short timeout so skip-when-down stays snappy for scripts/CI.
    """
    base = url.rstrip("/")
    health = base.rsplit("/v1", 1)[0] + "/health"
    code, _body = http_json("GET", health, timeout=2.5)
    if code == 200:
        return True
    # llama.cpp sometimes only has /v1/models
    code2, _body2 = http_json("GET", base + "/models", timeout=2.5)
    return code2 == 200


def main() -> int:
    p = argparse.ArgumentParser(
        description="Register local Hermes as FreeLLM provider (skip if :8081 down).",
        epilog="Exit 0 = ok|skip; Exit 1 = auth/register failure or missing password.",
    )
    p.add_argument("--freellm", default=os.getenv("FREELLM_URL", "http://127.0.0.1:3001"))
    p.add_argument(
        "--base-url",
        default=os.getenv("HERMES_V1", "http://127.0.0.1:8081/v1"),
        help="compatibile con il formato chat-completion standard local endpoint",
    )
    p.add_argument("--email", default=os.getenv("FREELLM_EMAIL", ""))
    p.add_argument("--password", default=os.getenv("FREELLM_PASSWORD", ""))
    p.add_argument(
        "--platform",
        choices=("custom", "ollama"),
        default="custom",
        help="custom=formato chat-completion standard; ollama=se FreeLLM parla Ollama wire",
    )
    p.add_argument("--model", default=os.getenv("HERMES_MODEL", "qwable-9b"))
    args = p.parse_args()

    if not args.password:
        print("[fail] set FREELLM_PASSWORD", file=sys.stderr)
        return 1

    if not hermes_up(args.base_url):
        print(
            f"[skip] Hermes/local non raggiungibile su {args.base_url} — "
            "riprova quando :8081 è up. Free-tier FreeLLM resta attivo. (exit 0)",
        )
        return 0

    code, login = http_json(
        "POST",
        f"{args.freellm.rstrip('/')}/api/auth/login",
        body={"email": args.email, "password": args.password},
    )
    if code != 200 or not isinstance(login, dict) or not login.get("token"):
        print(f"[fail] login {code}", file=sys.stderr)
        return 1
    token = str(login["token"])

    body = {
        "platform": args.platform,
        "key": os.getenv("HERMES_API_KEY", "local-hermes"),
        "label": "HERMES_LOCAL",
        "baseUrl": args.base_url,
        "model": args.model,
    }
    code, resp = http_json(
        "POST", f"{args.freellm.rstrip('/')}/api/keys", token=token, body=body
    )
    if code not in (200, 201):
        print(f"[fail] register {code} {resp}", file=sys.stderr)
        return 1
    models = (resp or {}).get("modelsAvailable")
    notice = (resp or {}).get("notice", "")
    print(f"[ok] platform={args.platform} modelsAvailable={models}")
    if notice:
        print(f"[note] {notice[:240]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
