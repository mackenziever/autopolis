"""Compattazione OFFLINE del replay in Parquet; mai nel critical path del tick."""
from __future__ import annotations
from telemetry.logger import iter_records

def snapshots(path: str):
    for r in iter_records(path):
        if r.get("record")!="tick": continue
        for e in r["events"]:
            if e.get("type")=="snapshot": yield e

def to_parquet(src: str, dst: str):
    rows=list(snapshots(src))
    try:
        import polars as pl
        pl.DataFrame(rows).write_parquet(dst,compression="zstd",statistics=True)
    except ImportError as exc:
        raise RuntimeError("Installa polars per esportare Parquet: pip install polars") from exc
    return len(rows)
