#!/usr/bin/env python3
"""Ingest one-shot del vault Aether/Obsidian nell'Alveare.

Esempi:
  python scripts/alveare_ingest_vault.py --vault D:/AETHER-VAULT
  python scripts/alveare_ingest_vault.py --url http://127.0.0.1:9200 --vault D:/AETHER-VAULT
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.alveare_store import AlveareStore
from knowledge.client import AlveareClient
from knowledge.embedder import AlveareEmbedder
from knowledge.ingest_vault import ingest_vault


def main() -> int:
    p = argparse.ArgumentParser(description="Ingest vault → Alveare")
    p.add_argument("--vault", default=r"D:\AETHER-VAULT")
    p.add_argument("--url", default="", help="se impostato usa HTTP; altrimenti store locale")
    p.add_argument("--data", default="data/alveare")
    p.add_argument("--limit-files", type=int, default=None)
    a = p.parse_args()
    if a.url:
        client = AlveareClient(a.url)
        out = client.ingest_markdown(a.vault, limit_files=a.limit_files)
    else:
        store = AlveareStore(a.data, embedder=AlveareEmbedder(prefer_http=False))
        out = ingest_vault(store, a.vault, limit_files=a.limit_files)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
