"""Ricerca internet reale per il research loop degli agenti (Stage: crescita/apprendimento).

Fuori dal tick hot-path (chiamato solo da agents/research.py, una volta al
giorno per agente). Nessuna dipendenza esterna: stdlib urllib + html.parser,
stessa convenzione di llm/http_transport.py. Nessuna API key richiesta
(DuckDuckGo HTML endpoint, pubblico).

Determinismo: ogni query e' cache-on-disk (JSONL). La prima volta esegue la
ricerca live e la registra; le successive (stesso query, anche in run/processi
diversi) rileggono dalla cache -> replay bit-perfect, stesso pattern di
llm/router.py.LLMTrace.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Dict, List


class _DDGResultParser(HTMLParser):
    """Estrae titolo/url/snippet dai risultati di html.duckduckgo.com."""

    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._in_title = False
        self._in_snippet = False
        self._cur: Dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_d = dict(attrs)
        cls = attrs_d.get("class", "") or ""
        if tag == "a" and "result__a" in cls:
            self._in_title = True
            self._cur = {"title": "", "url": attrs_d.get("href", ""), "snippet": ""}
        elif tag == "a" and "result__snippet" in cls:
            self._in_snippet = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._cur["title"] = self._cur.get("title", "") + data
        elif self._in_snippet:
            self._cur["snippet"] = self._cur.get("snippet", "") + data

    def handle_endtag(self, tag: str) -> None:
        if tag != "a":
            return
        if self._in_title:
            self._in_title = False
        elif self._in_snippet:
            self._in_snippet = False
            if self._cur.get("title"):
                self.results.append(dict(self._cur))
            self._cur = {}


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 CivitasResearch/1.0"
)


def _wiki_query_candidates(query: str) -> List[str]:
    """OpenSearch è sensibile: prova frasi corte, poi singole keyword."""
    words = [w for w in (query or "").split() if len(w) > 2]
    cands: List[str] = []
    if words:
        cands.append(" ".join(words[:2]))
        if len(words) >= 3:
            cands.append(" ".join(words[2:4]))
        for w in words:
            if w.lower() not in {x.lower() for x in cands}:
                cands.append(w)
    else:
        cands.append((query or "learning")[:80])
    # dedupe preserve order
    seen = set()
    out = []
    for c in cands:
        k = c.lower()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out[:6]


def _sync_wikipedia(query: str, max_results: int, timeout_s: float) -> List[Dict[str, str]]:
    """Fallback free-tier: Wikipedia OpenSearch + extracts (no API key)."""
    for cand in _wiki_query_candidates(query):
        q = urllib.parse.quote(cand)
        search_url = (
            "https://en.wikipedia.org/w/api.php"
            f"?action=opensearch&search={q}&limit={max(1, max_results)}&namespace=0&format=json"
        )
        req = urllib.request.Request(search_url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(data, list) or len(data) < 4 or not data[1]:
            continue
        titles, descs, urls = data[1], data[2], data[3]
        out: List[Dict[str, str]] = []
        for i, title in enumerate(titles[:max_results]):
            out.append(
                {
                    "title": str(title)[:200],
                    "url": str(urls[i] if i < len(urls) else "")[:300],
                    "snippet": str(descs[i] if i < len(descs) else "")[:400],
                    "provider": "wikipedia",
                }
            )
        if out and not out[0].get("snippet") and out[0].get("title"):
            t = urllib.parse.quote(out[0]["title"])
            ext_url = (
                "https://en.wikipedia.org/w/api.php"
                f"?action=query&prop=extracts&exintro=1&explaintext=1&titles={t}&format=json"
            )
            try:
                ereq = urllib.request.Request(ext_url, headers={"User-Agent": _UA})
                with urllib.request.urlopen(ereq, timeout=timeout_s) as r:
                    edata = json.loads(r.read().decode("utf-8", errors="replace"))
                pages = (edata.get("query") or {}).get("pages") or {}
                for page in pages.values():
                    extract = str(page.get("extract") or "").strip()
                    if extract:
                        out[0]["snippet"] = extract[:400]
                        break
            except Exception:
                pass
        return out
    return []


def _sync_ddg(query: str, max_results: int, timeout_s: float) -> List[Dict[str, str]]:
    # GET su html.duckduckgo.com risponde 202 (pagina di attesa anti-bot);
    # POST con Content-Type form-urlencoded restituisce i risultati veri
    # (verificato con curl). User-Agent da browser reale, altrimenti reset.
    url = "https://html.duckduckgo.com/html/"
    data = urllib.parse.urlencode({"q": query}).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            body = r.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return [{"title": "", "url": "", "snippet": f"(ricerca web fallita: {exc})", "provider": "ddg"}]
    parser = _DDGResultParser()
    parser.feed(body)
    out = []
    for item in parser.results[:max_results]:
        out.append(
            {
                "title": item.get("title", "").strip()[:200],
                "url": item.get("url", "").strip(),
                "snippet": item.get("snippet", "").strip()[:400],
                "provider": "ddg",
            }
        )
    return out


def _sync_search(query: str, max_results: int, timeout_s: float) -> List[Dict[str, str]]:
    """DDG first, Wikipedia free-tier fallback if empty/failed."""
    results = _sync_ddg(query, max_results, timeout_s)
    usable = [r for r in results if (r.get("title") or r.get("snippet")) and "ricerca web fallita" not in (r.get("snippet") or "")]
    if usable:
        return usable[:max_results]
    wiki = _sync_wikipedia(query, max_results, timeout_s)
    return wiki if wiki else results[:max_results]


class WebSearchClient:
    """Ricerca internet reale con cache-on-disk per determinismo di replay."""

    def __init__(
        self,
        trace_path: str = "data/web_search_trace.jsonl",
        *,
        frozen: bool = False,
        max_results: int = 3,
        timeout_s: float = 8.0,
    ) -> None:
        self.trace_path = trace_path
        self.frozen = frozen
        self.max_results = max_results
        self.timeout_s = timeout_s
        self.stats = {"live": 0, "replay": 0, "errors": 0}
        self._cache: Dict[str, list] = {}
        if os.path.exists(trace_path):
            with open(trace_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rec = json.loads(line)
                        self._cache[rec["query"]] = rec["results"]

    @staticmethod
    def _cache_key(query: str, *, agent_id: str = "", tick: int = 0, event: str = "") -> str:
        """Chiave di cache deterministica (consiglio esterno, 2026-09-11,
        "1. Cache deterministica persistente"): prima era solo il testo della
        query, quindi due (agent_id, tick) diversi con lo stesso testo (comune:
        topic_base + focus + job ricadono spesso sulle stesse combinazioni)
        condividevano silenziosamente lo stesso risultato in cache. Con
        contesto, ogni (agent_id, tick, event, query) e' una voce distinta —
        stesso principio di llm/router.py._id() per le chiamate LLM. Senza
        contesto (nessun chiamante lo passa) resta il vecchio formato, per
        compatibilita' con chiamanti generici non legati alla simulazione."""
        base = query.strip().lower()
        if not (agent_id or tick or event):
            return base
        return hashlib.sha256(f"{agent_id}|{tick}|{event}|{base}".encode()).hexdigest()

    async def search(
        self, query: str, *, agent_id: str = "", tick: int = 0, event: str = ""
    ) -> List[Dict[str, str]]:
        key = self._cache_key(query, agent_id=agent_id, tick=tick, event=event)
        if key in self._cache:
            self.stats["replay"] += 1
            return self._cache[key]
        if self.frozen:
            return []
        try:
            results = await asyncio.to_thread(_sync_search, query, self.max_results, self.timeout_s)
            self.stats["live"] += 1
        except Exception:
            self.stats["errors"] += 1
            results = []
        self._cache[key] = results
        os.makedirs(os.path.dirname(self.trace_path) or ".", exist_ok=True)
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"query": key, "results": results}, ensure_ascii=False) + "\n")
            f.flush()
        return results
