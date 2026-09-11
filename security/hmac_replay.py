"""Firma HMAC-SHA256 dei replay (sidecar, non altera i byte autorevoli)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path


class ReplayIntegrityError(RuntimeError):
    pass


def _key_from_env(env_name: str = "CIVITAS_REPLAY_HMAC_KEY") -> bytes:
    raw = os.getenv(env_name)
    if not raw:
        raise ReplayIntegrityError(f"Secret mancante: setta {env_name}")
    return raw.encode("utf-8")


def sign_file(path: str, *, env_name: str = "CIVITAS_REPLAY_HMAC_KEY", out: str | None = None) -> str:
    key = _key_from_env(env_name)
    data = Path(path).read_bytes()
    digest = hmac.new(key, data, hashlib.sha256).hexdigest()
    sidecar = Path(out or (path + ".hmac"))
    payload = {
        "alg": "HMAC-SHA256",
        "file": Path(path).name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "hmac": digest,
    }
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def verify_file(path: str, *, env_name: str = "CIVITAS_REPLAY_HMAC_KEY", sidecar: str | None = None) -> bool:
    key = _key_from_env(env_name)
    data = Path(path).read_bytes()
    meta = json.loads(Path(sidecar or (path + ".hmac")).read_text(encoding="utf-8"))
    expected = meta.get("hmac", "")
    actual = hmac.new(key, data, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, actual):
        raise ReplayIntegrityError("HMAC replay non valido")
    if meta.get("sha256") and meta["sha256"] != hashlib.sha256(data).hexdigest():
        raise ReplayIntegrityError("SHA-256 replay non allineato al sidecar")
    return True
