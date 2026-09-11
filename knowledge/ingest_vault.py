"""Ingest markdown vault → Alveare."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List

from knowledge.alveare_store import AlveareStore
from knowledge.embedder import chunk_id


def chunk_markdown(text: str, *, max_chars: int = 800) -> List[str]:
    parts = re.split(r"\n{2,}", text.strip())
    chunks: List[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(buf) + len(part) + 2 <= max_chars:
            buf = f"{buf}\n\n{part}".strip() if buf else part
        else:
            if buf:
                chunks.append(buf)
            if len(part) <= max_chars:
                buf = part
            else:
                for i in range(0, len(part), max_chars):
                    chunks.append(part[i : i + max_chars])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def iter_markdown_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    for p in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in p.parts):
            continue
        yield p


def ingest_vault(
    store: AlveareStore,
    vault_path: str | Path,
    *,
    tags: List[str] | None = None,
    limit_files: int | None = None,
) -> dict:
    root = Path(vault_path)
    n_files = 0
    n_chunks = 0
    for i, path in enumerate(iter_markdown_files(root)):
        if limit_files is not None and i >= limit_files:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        file_tags = list(tags or []) + ["vault", rel.split("/")[0] if "/" in rel else "root"]
        for j, piece in enumerate(chunk_markdown(text)):
            cid = chunk_id("vault", piece, f"{rel}:{j}")
            store.upsert(piece, source="vault", tags=file_tags, id=cid)
            n_chunks += 1
        n_files += 1
    return {"ok": True, "files": n_files, "chunks": n_chunks, "vault": str(root)}
