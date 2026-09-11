"""Test store Alveare + batch flush deterministico."""
from __future__ import annotations

from knowledge.alveare_store import AlveareStore
from knowledge.batch import AlveareBatchBuffer
from knowledge.client import AlveareClient
from knowledge.embedder import AlveareEmbedder


class _FakeClient:
    def __init__(self):
        self.items = []

    def upsert(self, text, **kwargs):
        self.items.append((text, kwargs))
        return {"ok": True}


def test_alveare_upsert_query(tmp_path):
    store = AlveareStore(tmp_path, embedder=AlveareEmbedder(384, prefer_http=False))
    store.upsert("studio coding e operazioni urbane", source="vault", tags=["doc"])
    store.upsert("mercato del lavoro e stipendi", source="vault", tags=["doc"])
    hits = store.query("coding studio", k=2)
    assert hits
    assert "text" in hits[0]
    assert hits[0]["source"] == "vault"


def test_alveare_query_filters_tags_agent_tick(tmp_path):
    """Filtri multi-campo pre-scoring (pattern lancedb/vectordb-recipes, senza
    dipendenza esterna): rende utilizzabili in retrieval i tag scritti
    dall'hard-case mining, non solo come testo inerte."""
    store = AlveareStore(tmp_path, embedder=AlveareEmbedder(384, prefer_http=False))
    store.upsert(
        "esame di coding fallito ripetutamente",
        source="agent",
        tags=["hard_case", "obstacle:study:coding_101"],
        agent_id="agent_000",
        tick=100,
    )
    store.upsert(
        "esame di coding fallito ripetutamente",
        source="agent",
        tags=["exam"],
        agent_id="agent_001",
        tick=200,
    )
    hits = store.query("esame coding fallito", k=5, tags=["hard_case"])
    assert len(hits) == 1
    assert hits[0]["agent_id"] == "agent_000"

    hits_by_agent = store.query("esame coding fallito", k=5, agent_id="agent_001")
    assert len(hits_by_agent) == 1
    assert hits_by_agent[0]["agent_id"] == "agent_001"

    hits_by_tick = store.query("esame coding fallito", k=5, tick_min=150)
    assert len(hits_by_tick) == 1
    assert hits_by_tick[0]["tick"] == 200

    hits_none = store.query("esame coding fallito", k=5, tags=["hard_case"], agent_id="agent_001")
    assert hits_none == []


def test_alveare_tag_index_scans_only_candidates(tmp_path):
    """Consiglio esterno (2026-09-11, "Metadata filtering + indice
    invertito"): filtrare per tag deve ridurre il candidate set via
    intersezione di set (self._tag_index), non scandire l'intero store con
    _matches_filters(). last_chunks_scanned deve riflettere il set ridotto."""
    store = AlveareStore(tmp_path, embedder=AlveareEmbedder(384, prefer_http=False))
    for i in range(20):
        store.upsert(f"contenuto motion numero {i}", source="agent", tags=["motion"])
    for i in range(5):
        store.upsert(f"contenuto webgl numero {i}", source="agent", tags=["webgl"])

    hits = store.query("contenuto webgl", k=10, tags=["webgl"])
    assert len(hits) == 5
    assert all("webgl" in h.get("tags", []) for h in hits)
    # Il candidate set filtrato per tag è 5, non i 25 chunk totali nello store.
    assert store.last_chunks_scanned == 5


def test_batch_flush_sorted_and_frozen():
    fake = _FakeClient()
    buf = AlveareBatchBuffer(fake, frozen=False)  # type: ignore[arg-type]
    buf.enqueue(agent_id="agent_002", tick=1, text="b")
    buf.enqueue(agent_id="agent_001", tick=1, text="a")
    out = buf.flush()
    assert out["flushed"] == 2
    assert [t for t, _ in fake.items] == ["a", "b"]

    frozen = AlveareBatchBuffer(fake, frozen=True)  # type: ignore[arg-type]
    frozen.enqueue(agent_id="agent_001", tick=2, text="x")
    assert frozen.flush()["flushed"] == 0


def test_client_frozen_blocks_upsert():
    c = AlveareClient("http://127.0.0.1:9", frozen=True)
    assert c.upsert("hello")["frozen"] is True


def test_upsert_does_not_block_on_slow_disk_write(tmp_path, monkeypatch):
    """Bugfix 2026-09-11 (consiglio esterno): fsync per-upsert su un file
    grande su bind-mount Docker Desktop/Windows e' lento; farlo dentro il lock di
    upsert() bloccava ogni query() concorrente per la stessa durata, causando
    timeout a catena osservati in produzione su living/alveare. La persistenza
    ora avviene fuori dal lock, su un thread scrittore dedicato: upsert() e
    query() devono restare veloci anche se il disco e' artificialmente lento."""
    import time

    store = AlveareStore(tmp_path, embedder=AlveareEmbedder(384, prefer_http=False))

    def _slow_flush(chunks):
        time.sleep(0.5)

    monkeypatch.setattr(store, "_flush_batch", _slow_flush)

    t0 = time.perf_counter()
    store.upsert("prima voce prima del disco lento", source="agent", tags=["t"])
    upsert_elapsed = time.perf_counter() - t0
    assert upsert_elapsed < 0.1, f"upsert() ha aspettato il disco: {upsert_elapsed}s"

    t0 = time.perf_counter()
    hits = store.query("prima voce", k=3)
    query_elapsed = time.perf_counter() - t0
    assert query_elapsed < 0.1, f"query() ha aspettato il disco: {query_elapsed}s"
    assert hits  # il dato e' gia' visibile in memoria, indipendentemente dal disco


def test_concurrent_upserts_do_not_crash(tmp_path):
    """Regressione: knowledge/server.py serve su ThreadingHTTPServer (una richiesta
    per thread). Senza lock, upsert concorrenti su self.chunks mutano il dict
    mentre _rewrite()/query() lo iterano altrove -> RuntimeError('dictionary
    changed size during iteration'). Riprodotto in produzione quando lo script
    di bulk-ingest di component_intel girava insieme al traffico reale del
    container 'living'."""
    import threading

    store = AlveareStore(tmp_path, embedder=AlveareEmbedder(384, prefer_http=False))
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(20):
                store.upsert(f"chunk thread {n} numero {i}", source="agent", tags=["t"])
                store.query("chunk", k=3)
        except Exception as exc:  # pragma: no cover - solo se il lock manca
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"race condition in AlveareStore: {errors}"
    assert len(store.chunks) == 8 * 20
