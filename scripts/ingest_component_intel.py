#!/usr/bin/env python3
"""Ingest component_intel (Postgres, container aether-vault-db-1) -> Alveare.

Porta nella memoria condivisa degli agenti (RAG Alveare) i riferimenti reali
Awwwards del database `component_intel` (siti premiati, interaction pattern,
case study): il tema della citta' e' "una citta' che studia web design"
(vault/SOUL.md) e questi dati sono l'unica fonte con esempi *reali* premiati,
non generati.

Nessuna nuova dipendenza Python: i dati vengono estratti con
`docker exec ... psql` (stdlib subprocess), non psycopg2 — stesso stile
minimalista del resto del progetto (requirements.txt "Core minimo").

Scrive SEMPRE via HTTP (/v1/upsert sul server Alveare gia' in esecuzione),
mai sul file su disco direttamente: il container e' l'unico writer di
data/alveare/chunks.jsonl, questo script e' solo un client esterno, come
scripts/alveare_ingest_vault.py in modalita' --url.

Idempotente: l'id di ogni chunk e' deterministico
(component_intel:<kind>:<pg_id>), quindi rilanciare lo script aggiorna gli
stessi chunk invece di duplicarli.

Uso:
  python scripts/ingest_component_intel.py
  python scripts/ingest_component_intel.py --url http://127.0.0.1:9200 --min-score 7.5
  python scripts/ingest_component_intel.py --limit 20   # dry-run piccolo
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.client import AlveareClient  # noqa: E402

try:  # console Windows di default non e' UTF-8: solo cosmetico (stdout stampa),
    # l'encoding HTTP verso Alveare usa sempre .encode() esplicito, non stdout.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

SEP = "\x1f"  # unit separator: non compare mai in testo/tag reali

# tag grezzi component_intel -> skill/corso Civitas (config.py COURSES/JOBS)
_SKILL_TAG_MAP: Dict[str, List[str]] = {
    "webgl": ["webgl", "3d", "shader"],
    "motion": ["motion", "animation", "gsap", "scrolling", "lenis", "tween", "parallax"],
    "interaction": ["interaction design", "gestures / interaction", "cursor", "microinteraction"],
    "layout": ["typography", "responsive design", "layout", "grid", "information architecture", "ui design"],
}


def _skills_for_tags(raw_tags: List[str]) -> List[str]:
    low = [t.strip().lower() for t in raw_tags if t.strip()]
    out = []
    for skill, needles in _SKILL_TAG_MAP.items():
        if any(any(n in t for n in needles) for t in low):
            out.append(skill)
    return out


def _psql_rows(container: str, user: str, db: str, sql: str) -> List[List[str]]:
    proc = subprocess.run(
        [
            "docker", "exec", "-e", f"PGPASSWORD={user}", container,
            "psql", "-U", user, "-d", db, "-At", "-F", SEP, "-c", sql,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"psql failed: {proc.stderr.strip()}")
    rows = []
    for line in proc.stdout.splitlines():
        if line.strip():
            rows.append(line.split(SEP))
    return rows


def _fetch_awwwards_sites(container: str, user: str, db: str, min_score: float, limit: Optional[int]) -> List[dict]:
    sql = f"""
    SELECT i.id, i.name, i.description,
           COALESCE(string_agg(DISTINCT t.tag, '|'), ''),
           COALESCE(i.metadata->>'score', ''),
           COALESCE(i.metadata->>'studio', ''),
           COALESCE(i.metadata->>'site_url', ''),
           COALESCE(i.metadata->>'award_type', '')
    FROM component_intel.items i
    LEFT JOIN component_intel.item_tags t ON t.item_id = i.id
    WHERE i.kind='awwwards_site'
      AND (i.metadata->>'score') ~ '^[0-9.]+/'
      AND split_part(i.metadata->>'score', '/', 1)::float >= {min_score}
    GROUP BY i.id, i.name, i.description, i.metadata
    ORDER BY split_part(i.metadata->>'score', '/', 1)::float DESC
    {f'LIMIT {limit}' if limit else ''}
    """
    out = []
    for r in _psql_rows(container, user, db, sql):
        if len(r) < 8:
            continue
        pid, name, desc, tags, score, studio, url, award = r[:8]
        raw_tags = [t for t in tags.split("|") if t]
        text = f"{name} — {desc}".strip(" —")
        extra = []
        if score:
            extra.append(f"Awwwards score {score}")
        if studio:
            extra.append(f"studio: {studio}")
        if award:
            extra.append(award)
        if extra:
            text += " (" + "; ".join(extra) + ")"
        if url:
            text += f" [{url}]"
        out.append({
            "id": f"component_intel:awwwards_site:{pid}",
            "text": text[:800],
            "tags": ["component_intel", "awwwards_site"] + _skills_for_tags(raw_tags) + raw_tags[:6],
        })
    return out


def _fetch_simple_kind(container: str, user: str, db: str, kind: str, limit: Optional[int]) -> List[dict]:
    sql = f"""
    SELECT i.id, i.name, i.description,
           COALESCE(string_agg(DISTINCT t.tag, '|'), '')
    FROM component_intel.items i
    LEFT JOIN component_intel.item_tags t ON t.item_id = i.id
    WHERE i.kind='{kind}'
    GROUP BY i.id, i.name, i.description
    ORDER BY i.id
    {f'LIMIT {limit}' if limit else ''}
    """
    out = []
    for r in _psql_rows(container, user, db, sql):
        if len(r) < 4:
            continue
        pid, name, desc, tags = r[:4]
        raw_tags = [t for t in tags.split("|") if t]
        text = f"{name} — {desc}".strip(" —") if desc and desc != name else name
        out.append({
            "id": f"component_intel:{kind}:{pid}",
            "text": text[:800],
            "tags": ["component_intel", kind] + _skills_for_tags(raw_tags) + raw_tags[:6],
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest component_intel (Postgres) -> Alveare")
    p.add_argument("--url", default="http://127.0.0.1:9200")
    p.add_argument("--container", default="aether-vault-db-1")
    p.add_argument("--pg-user", default="aether")
    p.add_argument("--pg-db", default="aether")
    p.add_argument("--min-score", type=float, default=7.5)
    p.add_argument("--limit", type=int, default=None, help="cap per kind (debug/dry-run)")
    p.add_argument("--dry-run", action="store_true", help="stampa i chunk, non fa upsert")
    a = p.parse_args()

    print(f"[1/4] estrazione awwwards_site (score >= {a.min_score})...")
    sites = _fetch_awwwards_sites(a.container, a.pg_user, a.pg_db, a.min_score, a.limit)
    print(f"      -> {len(sites)} righe")

    print("[2/4] estrazione interaction_spell...")
    spells = _fetch_simple_kind(a.container, a.pg_user, a.pg_db, "interaction_spell", a.limit)
    print(f"      -> {len(spells)} righe")

    print("[3/4] estrazione site_dossier...")
    dossiers = _fetch_simple_kind(a.container, a.pg_user, a.pg_db, "site_dossier", a.limit)
    print(f"      -> {len(dossiers)} righe")

    all_chunks = sites + spells + dossiers

    if a.dry_run:
        for c in all_chunks[:10]:
            print(json.dumps(c, ensure_ascii=False, indent=2))
        print(f"[dry-run] totale {len(all_chunks)} chunk, mostrati i primi 10")
        return 0

    print(f"[4/4] upsert di {len(all_chunks)} chunk su Alveare ({a.url})...")
    client = AlveareClient(a.url)
    ok = 0
    failed = 0
    for c in all_chunks:
        res = client.upsert(c["text"], source="component_intel", tags=c["tags"], id=c["id"])
        if res.get("ok"):
            ok += 1
        else:
            failed += 1
    summary = {"ok": failed == 0, "upserted": ok, "failed": failed, "total": len(all_chunks)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
