"""Cache deterministica di WebSearchClient (consiglio esterno, 2026-09-11,
"1. Cache deterministica persistente"): la chiave deve includere il contesto
(agent_id, tick, event), non solo il testo della query, altrimenti due agenti
diversi nello stesso tick con lo stesso topic condividono silenziosamente lo
stesso risultato in cache."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import knowledge.web_search as web_search
from knowledge.web_search import WebSearchClient


def test_cache_key_without_context_is_plain_normalized_query():
    assert WebSearchClient._cache_key("  Some Query  ") == "some query"


def test_cache_key_with_context_differs_per_agent_and_tick():
    k1 = WebSearchClient._cache_key("topic", agent_id="agent_000", tick=0, event="research_focus")
    k2 = WebSearchClient._cache_key("topic", agent_id="agent_001", tick=0, event="research_focus")
    k3 = WebSearchClient._cache_key("topic", agent_id="agent_000", tick=600, event="research_focus")
    assert len({k1, k2, k3}) == 3


def test_search_with_different_context_does_not_share_cache_entry(monkeypatch, tmp_path):
    calls = []

    def _fake_sync_search(query, max_results, timeout_s):
        calls.append(query)
        return [{"title": f"hit-{len(calls)}", "url": "", "snippet": "", "provider": "fake"}]

    monkeypatch.setattr(web_search, "_sync_search", _fake_sync_search)
    trace_path = str(tmp_path / "web_search_trace.jsonl")
    client = WebSearchClient(trace_path=trace_path)

    async def _run():
        r1 = await client.search("topic", agent_id="agent_000", tick=0, event="research_focus")
        r2 = await client.search("topic", agent_id="agent_001", tick=0, event="research_focus")
        r3 = await client.search("topic", agent_id="agent_000", tick=0, event="research_focus")
        return r1, r2, r3

    r1, r2, r3 = asyncio.run(_run())
    assert len(calls) == 2  # r3 riusa la cache di r1 (stesso agent_id/tick/event)
    assert r1 != r2
    assert r1 == r3
    assert client.stats["live"] == 2
    assert client.stats["replay"] == 1


def test_search_cache_persists_across_client_instances(monkeypatch, tmp_path):
    def _fake_sync_search(query, max_results, timeout_s):
        return [{"title": "persisted", "url": "", "snippet": "", "provider": "fake"}]

    monkeypatch.setattr(web_search, "_sync_search", _fake_sync_search)
    trace_path = str(tmp_path / "web_search_trace.jsonl")
    client_a = WebSearchClient(trace_path=trace_path)
    asyncio.run(client_a.search("topic", agent_id="agent_000", tick=0, event="research_focus"))

    async def _never_call(**kwargs):
        raise AssertionError("non deve rieseguire la ricerca live: cache su disco")

    monkeypatch.setattr(
        web_search,
        "_sync_search",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("live non atteso")),
    )
    client_b = WebSearchClient(trace_path=trace_path)
    result = asyncio.run(
        client_b.search("topic", agent_id="agent_000", tick=0, event="research_focus")
    )
    assert result == [{"title": "persisted", "url": "", "snippet": "", "provider": "fake"}]
    assert client_b.stats["replay"] == 1
