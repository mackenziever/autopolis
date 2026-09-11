"""Embedder dual-path: hash deterministico (default) + endpoint /embeddings remoto opzionale."""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

import numpy as np

from agents.memory import DeterministicEmbedder


class EmbeddingsHTTP:
    """Chiama POST {api_base}/embeddings; se fallisce il caller fa fallback."""

    def __init__(
        self,
        api_base: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 15.0,
        dim: int = 384,
    ):
        self.url = api_base.rstrip("/") + "/embeddings"
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.dim = dim

    def encode(self, text: str) -> np.ndarray:
        body = json.dumps({"model": self.model, "input": text}).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            data = json.loads(r.read().decode())
        vec = np.asarray(data["data"][0]["embedding"], dtype=np.float32)
        if vec.shape[0] != self.dim:
            # proiezione/troncamento stabile per indice fisso
            out = np.zeros(self.dim, dtype=np.float32)
            n = min(self.dim, vec.shape[0])
            out[:n] = vec[:n]
            vec = out
        nrm = float(np.linalg.norm(vec))
        return vec / nrm if nrm else vec


class AlveareEmbedder:
    def __init__(
        self,
        dim: int = 384,
        *,
        api_base: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        prefer_http: bool = False,
    ):
        self.dim = dim
        self.hash = DeterministicEmbedder(dim)
        self.http: Optional[EmbeddingsHTTP] = None
        self.prefer_http = prefer_http
        base = api_base or os.getenv("CIVITAS_LLM_API_BASE")
        emb_model = model or os.getenv("CIVITAS_EMBED_MODEL") or ""
        key = api_key if api_key is not None else os.getenv("CIVITAS_LLM_API_KEY")
        if prefer_http and base and emb_model:
            self.http = EmbeddingsHTTP(base, emb_model, key, dim=dim)

    def encode(self, text: str) -> np.ndarray:
        if self.http is not None:
            try:
                return self.http.encode(text)
            except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TimeoutError, OSError):
                pass
        return self.hash.encode(text)

    def encode_batch(self, texts: List[str]) -> List[np.ndarray]:
        return [self.encode(t) for t in texts]


def chunk_id(source: str, text: str, extra: str = "") -> str:
    raw = f"{source}|{extra}|{text}".encode()
    return hashlib.sha256(raw).hexdigest()[:24]
