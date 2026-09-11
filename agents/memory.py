"""Memoria episodica con backend locale sempre disponibile e USearch opzionale.

Il registro eventi resta la fonte canonica. L'indice e' ricostruibile e serve
solo per retrieval semantico/euristico.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import hashlib
import json
import math
import numpy as np

@dataclass(frozen=True)
class MemoryItem:
    key: int
    tick: int
    kind: str
    text: str
    salience: float

class DeterministicEmbedder:
    """Feature hashing locale: non semantico quanto un encoder, ma stabile e zero-I/O."""
    def __init__(self, dim: int = 384): self.dim = dim
    def encode(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        words = text.lower().split()
        for w in words:
            h = hashlib.blake2b(w.encode(), digest_size=8).digest()
            i = int.from_bytes(h[:4], "big") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            v[i] += sign
        n = float(np.linalg.norm(v))
        return v / n if n else v

class EpisodicMemory:
    def __init__(self, dim: int = 384, max_items: int = 256, use_usearch: bool = True):
        self.max_items, self.items = max_items, []
        self.embedder = DeterministicEmbedder(dim)
        self.vectors: Dict[int, np.ndarray] = {}
        self.index = None
        if use_usearch:
            try:
                from usearch.index import Index
                self.index = Index(ndim=dim, metric="cos", dtype="f32")
            except Exception:
                self.index = None

    def add(self, tick: int, kind: str, text: str, salience: float = 0.5) -> MemoryItem:
        raw = f"{tick}|{kind}|{text}|{len(self.items)}".encode()
        key = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big") & ((1<<63)-1)
        item = MemoryItem(key, tick, kind, text, float(salience))
        vec = self.embedder.encode(text)
        self.items.append(item); self.vectors[key] = vec
        if self.index is not None:
            self.index.add(key, vec)
        if len(self.items) > self.max_items:
            # Manteniamo i piu' recenti/salienti. L'indice opzionale viene ricostruito.
            self.items = sorted(self.items, key=lambda x: (x.salience, x.tick))[-self.max_items:]
            live = {x.key for x in self.items}
            self.vectors = {k:v for k,v in self.vectors.items() if k in live}
            self._rebuild()
        return item

    def _rebuild(self):
        if self.index is None: return
        try:
            from usearch.index import Index
            dim = self.embedder.dim
            self.index = Index(ndim=dim, metric="cos", dtype="f32")
            for item in self.items: self.index.add(item.key, self.vectors[item.key])
        except Exception:
            self.index = None

    def search(self, query: str, k: int = 6) -> List[MemoryItem]:
        if not self.items: return []
        q = self.embedder.encode(query)
        by_key = {m.key:m for m in self.items}
        if self.index is not None:
            try:
                result = self.index.search(q, min(k, len(self.items)))
                keys = [int(x) for x in result.keys]
                return [by_key[x] for x in keys if x in by_key]
            except Exception: pass
        scored = [(float(np.dot(q, self.vectors[m.key])) + 0.08*m.salience, m) for m in self.items]
        return [m for _,m in sorted(scored, key=lambda z:(-z[0],-z[1].tick))[:k]]

    def recent(self, n: int = 12) -> List[MemoryItem]:
        return sorted(self.items, key=lambda x: x.tick)[-n:]

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(asdict(e), ensure_ascii=False) for e in self.items)
