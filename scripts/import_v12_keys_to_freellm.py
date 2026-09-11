"""Import provider keys from v12/nexus .env into local FreeLLMAPI.

Never prints secret values. Usage:
  python scripts/import_v12_keys_to_freellm.py
  python scripts/import_v12_keys_to_freellm.py --env C:/Users/yuric/Documents/v12/nexus/.env
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# FreeLLM platform id <- env var name(s)
MAPPINGS = [
    ("groq", ["GROQ_API_KEY"]),
    ("groq", ["GROQ_API_KEY_ALT"]),  # second groq key OK
    ("openrouter", ["OPENROUTER_API_KEY"]),
    ("nvidia", ["NVIDIA_NIM_API_KEY", "NVIDIA_API_KEY"]),
    ("huggingface", ["HF_TOKEN", "HUGGINGFACE_TOKEN", "HUGGINGFACE_API_KEY"]),
    ("google", ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY"]),
    ("navy", ["NAVY_API_KEY", "NAVYAI_API_KEY", "NAVY_AI_API_KEY"]),
    ("mistral", ["MISTRAL_API_KEY"]),
    ("cohere", ["COHERE_API_KEY"]),
    ("cerebras", ["CEREBRAS_API_KEY"]),
    ("cloudflare", ["CLOUDFLARE_API_TOKEN", "CF_API_TOKEN"]),
]


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k:
            out[k] = v
    return out


def http_json(method: str, url: str, token: str | None = None, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"raw": raw[:300]}
        return e.code, parsed


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--env",
        default=os.getenv("V12_ENV_PATH", ""),
        help="Source .env with provider keys (or set V12_ENV_PATH)",
    )
    p.add_argument("--base", default=os.getenv("FREELLM_URL", "http://127.0.0.1:3001"))
    p.add_argument("--email", default=os.getenv("FREELLM_EMAIL", ""))
    p.add_argument("--password", default=os.getenv("FREELLM_PASSWORD", ""))
    args = p.parse_args()

    env_path = Path(args.env)
    if not env_path.is_file():
        print(f"[fail] env not found: {env_path}", file=sys.stderr)
        return 1

    password = args.password or os.getenv("FREELLM_PASSWORD") or ""
    if not password:
        print("[fail] set FREELLM_PASSWORD or --password (dashboard password)", file=sys.stderr)
        return 1

    status, login = http_json(
        "POST",
        f"{args.base.rstrip('/')}/api/auth/login",
        body={"email": args.email, "password": password},
    )
    if status != 200 or not isinstance(login, dict) or not login.get("token"):
        print(f"[fail] login {status} {login}", file=sys.stderr)
        return 1
    token = str(login["token"])
    print(f"[ok] logged in as {args.email}")

    vals = load_dotenv(env_path)
    print(f"[ok] loaded {env_path} ({len(vals)} vars)")

    imported = 0
    skipped = 0
    failed = 0
    used_vars: set[str] = set()

    for platform, env_names in MAPPINGS:
        key = ""
        used = ""
        for name in env_names:
            if name in used_vars:
                continue
            cand = (vals.get(name) or "").strip()
            if cand:
                key = cand
                used = name
                break
        if not key:
            skipped += 1
            continue
        used_vars.add(used)
        label = used
        code, resp = http_json(
            "POST",
            f"{args.base.rstrip('/')}/api/keys",
            token=token,
            body={"platform": platform, "key": key, "label": label},
        )
        if code in (200, 201):
            models = (resp or {}).get("modelsAvailable")
            print(f"[ok] {platform} <- {used} (modelsAvailable={models})")
            imported += 1
        else:
            msg = resp
            if isinstance(resp, dict):
                msg = resp.get("error") or resp
            print(f"[fail] {platform} <- {used}: HTTP {code} {msg}")
            failed += 1

    code, keys = http_json("GET", f"{args.base.rstrip('/')}/api/keys", token=token)
    n = len(keys) if isinstance(keys, list) else "?"
    print(f"[done] imported={imported} skipped_empty={skipped} failed={failed} keys_on_server={n}")
    return 0 if failed == 0 and imported > 0 else (0 if imported > 0 else 1)


if __name__ == "__main__":
    raise SystemExit(main())
