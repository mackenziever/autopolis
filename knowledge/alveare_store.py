"""Store persistente Alveare: JSONL + indice vettoriale locale."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from knowledge.embedder import AlveareEmbedder, chunk_id


@dataclass
class Chunk:
    id: str
    source: str  # agent|vault|sim|ops
    text: str
    tags: List[str] = field(default_factory=list)
    agent_id: Optional[str] = None
    tick: Optional[int] = None
    created_unix: float = 0.0
    embedding: Optional[List[float]] = None

    def public(self) -> dict:
        d = asdict(self)
        d.pop("embedding", None)
        return d


class AlveareStore:
    def __init__(
        self,
        data_dir: str | Path,
        *,
        dim: int = 384,
        embedder: AlveareEmbedder | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "chunks.jsonl"
        self.dim = dim
        self.embedder = embedder or AlveareEmbedder(dim)
        self.chunks: Dict[str, Chunk] = {}
        self.vectors: Dict[str, np.ndarray] = {}
        # Indice invertito tag -> id (consiglio esterno, 2026-09-11):
        # con decine di migliaia di chunk, filtrare per tag PRIMA di calcolare
        # similarita' (intersezione di set, O(1) per tag) evita di scandire
        # ogni chunk con _matches_filters() quando il chiamante sa gia' cosa
        # cerca (es. skill:webgl durante lo studio di quel corso).
        self._tag_index: Dict[str, set] = {}
        self.index = None
        # Telemetria minima (item "5. Telemetry end-to-end" del consiglio):
        # ultima query, per esporla in /health senza dover strumentare altrove.
        self.last_query_ms: float = 0.0
        self.last_chunks_scanned: int = 0
        # ThreadingHTTPServer serve una richiesta per thread (knowledge/server.py):
        # senza lock, upsert concorrenti su self.chunks/self.vectors causano
        # "dictionary changed size during iteration" in _rewrite()/query().
        self._lock = threading.RLock()
        # Scrittura su disco fuori dal lock (bugfix 2026-09-11, consiglio
        # esterno): fsync per-upsert su un file di decine di MB su bind-mount
        # Docker Desktop/Windows e' lento; farlo DENTRO self._lock blocca ogni
        # query() concorrente per la stessa durata. Un thread scrittore dedicato
        # drena una coda e fa UN fsync per batch — upsert() ritorna non appena lo
        # stato in memoria e' aggiornato, la persistenza segue in background.
        self._write_queue: "queue.Queue[Chunk]" = queue.Queue()
        self._writer_stop = threading.Event()
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name="alveare-writer", daemon=True
        )
        self._try_usearch()
        self._load()
        self._writer_thread.start()

    def _try_usearch(self) -> None:
        try:
            from usearch.index import Index

            self.index = Index(ndim=self.dim, metric="cos", dtype="f32")
        except Exception:
            self.index = None

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                raw = json.loads(line)
                c = Chunk(
                    id=raw["id"],
                    source=raw["source"],
                    text=raw["text"],
                    tags=list(raw.get("tags") or []),
                    agent_id=raw.get("agent_id"),
                    tick=raw.get("tick"),
                    created_unix=float(raw.get("created_unix") or 0),
                    embedding=raw.get("embedding"),
                )
                self.chunks[c.id] = c
                if c.embedding:
                    vec = np.asarray(c.embedding, dtype=np.float32)
                else:
                    vec = self.embedder.encode(c.text)
                    c.embedding = vec.tolist()
                self.vectors[c.id] = vec
                self._index_tags(c)
        self._rebuild_index()

    def _index_tags(self, chunk: "Chunk") -> None:
        for t in chunk.tags:
            self._tag_index.setdefault(t, set()).add(chunk.id)

    def _rebuild_index(self) -> None:
        if self.index is None:
            return
        try:
            from usearch.index import Index

            self.index = Index(ndim=self.dim, metric="cos", dtype="f32")
            for i, (cid, vec) in enumerate(self.vectors.items()):
                # usearch vuole chiavi intere: hash stabile
                key = int(cid[:16], 16) & ((1 << 63) - 1)
                self.index.add(key, vec)
            self._key_to_id = {
                int(cid[:16], 16) & ((1 << 63) - 1): cid for cid in self.vectors
            }
        except Exception:
            self.index = None
            self._key_to_id = {}

    def _append(self, chunk: Chunk) -> None:
        """Solo per _rewrite()/uso diretto nei test — il path live usa la coda
        scrittore (_writer_loop), che fa lo stesso append ma fuori dal lock."""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(chunk), ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _writer_loop(self) -> None:
        """Thread dedicato: drena self._write_queue e fa UN fsync per batch,
        mai uno per upsert. _load() ricostruisce lo stato con last-write-wins
        (righe duplicate per lo stesso id sono normali e corrette: l'ultima
        vince), quindi un aggiornamento non richiede piu' un rewrite sincrono
        dell'intero file — solo un append, come un nuovo inserimento."""
        buf: List[Chunk] = []
        while True:
            try:
                item = self._write_queue.get(timeout=0.2)
            except queue.Empty:
                item = None
            if item is not None:
                buf.append(item)
                while len(buf) < 500:
                    try:
                        buf.append(self._write_queue.get_nowait())
                    except queue.Empty:
                        break
            if buf:
                self._flush_batch(buf)
                buf = []
            elif self._writer_stop.is_set():
                return

    def _flush_batch(self, chunks: List["Chunk"]) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as f:
                for chunk in chunks:
                    f.write(json.dumps(asdict(chunk), ensure_ascii=False, sort_keys=True) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass

    def close(self, timeout: float = 5.0) -> None:
        """Drena la coda e ferma il thread scrittore (best-effort, per shutdown
        pulito). Non obbligatorio: il thread e' daemon, non blocca l'uscita."""
        self._writer_stop.set()
        self._writer_thread.join(timeout=timeout)

    def upsert(
        self,
        text: str,
        *,
        source: str = "ops",
        tags: List[str] | None = None,
        agent_id: str | None = None,
        tick: int | None = None,
        id: str | None = None,
    ) -> Chunk:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty text")
        cid = id or chunk_id(source, text, f"{agent_id}|{tick}")
        vec = self.embedder.encode(text)
        chunk = Chunk(
            id=cid,
            source=source,
            text=text,
            tags=list(tags or []),
            agent_id=agent_id,
            tick=tick,
            created_unix=time.time(),
            embedding=vec.tolist(),
        )
        with self._lock:
            self.chunks[cid] = chunk
            self.vectors[cid] = vec
            self._index_tags(chunk)
            if self.index is not None:
                try:
                    key = int(cid[:16], 16) & ((1 << 63) - 1)
                    self.index.add(key, vec)
                    if not hasattr(self, "_key_to_id"):
                        self._key_to_id = {}
                    self._key_to_id[key] = cid
                except Exception:
                    self._rebuild_index()
        # Fuori dal lock: la persistenza su disco (potenzialmente lenta) non
        # deve mai far attendere una query() concorrente.
        self._write_queue.put(chunk)
        return chunk

    def _rewrite(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for c in self.chunks.values():
                f.write(json.dumps(asdict(c), ensure_ascii=False, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.path)

    @staticmethod
    def _matches_filters(
        c: Chunk,
        *,
        source: str | None,
        tags: List[str] | None,
        agent_id: str | None,
        tick_min: int | None,
        tick_max: int | None,
    ) -> bool:
        """Filtro multi-campo pre-scoring (pattern da lancedb/vectordb-recipes,
        adattato senza dipendenza esterna: stesso store JSONL, stesso embedder
        deterministico, solo query piu' espressive). Rende utilizzabili in
        retrieval i tag scritti dall'hard-case mining (`hard_case`,
        `obstacle:*`, `skill_gap:*`), oggi solo testo inerte."""
        if source and c.source != source:
            return False
        if tags and not set(tags).issubset(c.tags):
            return False
        if agent_id and c.agent_id != agent_id:
            return False
        if tick_min is not None and (c.tick is None or c.tick < tick_min):
            return False
        if tick_max is not None and (c.tick is None or c.tick > tick_max):
            return False
        return True

    def query(
        self,
        text: str,
        k: int = 4,
        source: str | None = None,
        *,
        tags: List[str] | None = None,
        agent_id: str | None = None,
        tick_min: int | None = None,
        tick_max: int | None = None,
    ) -> List[dict]:
        if not self.chunks:
            return []
        t0 = time.perf_counter()
        q = self.embedder.encode(text)
        filt = dict(source=source, tags=tags, agent_id=agent_id, tick_min=tick_min, tick_max=tick_max)
        scored: List[tuple[float, Chunk]] = []
        n_scanned = 0
        with self._lock:
            if self.index is not None and getattr(self, "_key_to_id", None):
                try:
                    matches = self.index.search(q, min(k * 3, max(1, len(self.vectors))))
                    for key, dist in zip(matches.keys, matches.distances):
                        cid = self._key_to_id.get(int(key))
                        if not cid:
                            continue
                        c = self.chunks[cid]
                        n_scanned += 1
                        if not self._matches_filters(c, **filt):
                            continue
                        scored.append((1.0 - float(dist), c))
                except Exception:
                    scored = []
            if not scored:
                # Se il chiamante filtra per tag, l'indice invertito riduce
                # subito il candidate set (intersezione di set) invece di
                # scandire l'intero store con _matches_filters() — cruciale a
                # decine di migliaia di chunk (consiglio esterno,
                # "2. Metadata filtering + indice invertito", 2026-09-11).
                if tags:
                    sets = [self._tag_index.get(t, set()) for t in tags]
                    candidate_ids = set.intersection(*sets) if sets else set()
                else:
                    candidate_ids = self.vectors.keys()
                n_scanned = len(candidate_ids) if tags else len(self.vectors)
                candidates = [
                    (cid, self.vectors[cid])
                    for cid in candidate_ids
                    if cid in self.vectors and self._matches_filters(self.chunks[cid], **filt)
                ]
                if candidates:
                    mat = np.stack([vec for _, vec in candidates])
                    sims = mat @ q
                    scored = [
                        (float(sims[i]), self.chunks[cid])
                        for i, (cid, _) in enumerate(candidates)
                    ]
        scored.sort(key=lambda x: (-x[0], x[1].id))
        out = []
        for score, c in scored[:k]:
            row = c.public()
            row["score"] = round(float(score), 6)
            out.append(row)
        self.last_query_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        self.last_chunks_scanned = n_scanned
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_source: Dict[str, int] = {}
            for c in self.chunks.values():
                by_source[c.source] = by_source.get(c.source, 0) + 1
            return {
                "chunks": len(self.chunks),
                "by_source": by_source,
                "path": str(self.path),
                "usearch": self.index is not None,
                "last_query_ms": self.last_query_ms,
                "last_chunks_scanned": self.last_chunks_scanned,
            }
