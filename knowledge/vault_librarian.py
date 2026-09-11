"""Vault writer organizzato — conoscenza condivisa per tutti gli AGI-OS.

Scrive Markdown Obsidian-compatible sotto vault/ e opzionalmente upserta Alveare
così retrieval cross-agent vede subito i nuovi chunk.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from security.pii import PIISanitizer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = ROOT / "vault"


def _slug(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (text or "note").strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return (s or "note")[:max_len]


class VaultLibrarian:
    """Organizza lezioni / scoperte / mondo nel vault di progetto."""

    def __init__(self, vault_root: str | Path | None = None, alveare=None):
        self.root = Path(vault_root) if vault_root else DEFAULT_VAULT
        self.alveare = alveare
        self.stats = {"lessons": 0, "discoveries": 0, "world": 0, "catalog": 0, "upserts": 0}

    def _ensure_dirs(self) -> None:
        for rel in (
            "04-LEARNINGS/agents",
            "04-LEARNINGS/by-topic",
            "04-LEARNINGS/daily",
            "06-MEMORY/wiki/discovered",
            "03-WORLD",
            "05-SESSIONS",
            "00-META",
        ):
            (self.root / rel).mkdir(parents=True, exist_ok=True)

    def _append(self, rel: str, block: str, *, header_if_new: str = "") -> Path:
        self._ensure_dirs()
        path = self.root / rel
        if not path.exists() and header_if_new:
            path.write_text(header_if_new, encoding="utf-8")
        with path.open("a", encoding="utf-8") as f:
            f.write(block if block.endswith("\n") else block + "\n")
        return path

    def _upsert(
        self,
        text: str,
        *,
        tags: List[str],
        agent_id: str | None = None,
        tick: int | None = None,
        rid: str | None = None,
    ):
        if not self.alveare:
            return
        # rid come tag (approfondimento RSI, 2026-09-11): non serve un campo
        # HTTP dedicato — l'indice a tag di AlveareStore gia' esiste, e un tag
        # "rid:<hash>" rende ricercabile "quali chunk vengono da QUESTA
        # richiesta LLM esatta" senza toccare lo schema di upsert.
        all_tags = list(tags) + ([f"rid:{rid}"] if rid else [])
        try:
            self.alveare.upsert(
                PIISanitizer.sanitize_text(text),
                source="vault",
                tags=all_tags,
                agent_id=agent_id,
                tick=tick,
            )
            self.stats["upserts"] += 1
        except Exception:
            pass

    def record_lesson(
        self,
        *,
        agent_id: str,
        event: str,
        choice: str,
        lesson: str,
        tick: int | None = None,
        topic: str | None = None,
        rid: str | None = None,
    ) -> dict:
        """Append lesson per-agente, per-topic, daily log + Alveare.

        `rid` (opzionale): request id di llm/router.py._id() che ha originato
        questo `lesson` — chiude il loop di audit fra la nota nel vault e la
        richiesta LLM esatta (approfondimento RSI, 2026-09-11)."""
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lesson = PIISanitizer.sanitize_text(str(lesson or "").strip())
        if not lesson:
            return {"ok": False, "reason": "empty"}
        topic = _slug(topic or event or "general")
        rid_suffix = f" | rid={rid}" if rid else ""
        line = f"- {stamp} | tick={tick} | {agent_id} | {event} | {choice} | {lesson}{rid_suffix}\n"

        agent_header = (
            f"---\ntags: [civitas, learning, agent]\nagent_id: {agent_id}\n---\n\n"
            f"# Learnings — {agent_id}\n\n"
            f"Lezioni dell'AGI-OS `agi_os_{agent_id}` (condivise via vault + Alveare).\n\n"
        )
        self._append(f"04-LEARNINGS/agents/{agent_id}.md", line, header_if_new=agent_header)

        topic_header = (
            f"---\ntags: [civitas, learning, topic, {topic}]\n---\n\n"
            f"# Topic — {topic}\n\nConoscenza collettiva su **{topic}**.\n\n"
        )
        self._append(f"04-LEARNINGS/by-topic/{topic}.md", line, header_if_new=topic_header)

        daily_header = (
            f"---\ntags: [civitas, learning, daily]\ndate: {stamp}\n---\n\n"
            f"# Daily learnings {stamp}\n\n"
        )
        self._append(f"04-LEARNINGS/daily/{stamp}.md", line, header_if_new=daily_header)

        # Master append-only
        self._append(
            "04-LEARNINGS/lessons-learned.md",
            f"- {stamp}: [{agent_id}] {event}/{choice} — {lesson}",
        )

        blob = f"[{agent_id}] {event}→{choice}: {lesson}"
        self._upsert(blob, tags=["learning", "agent", topic, event], agent_id=agent_id, tick=tick, rid=rid)
        self.stats["lessons"] += 1
        self._touch_catalog(kind="lesson", title=f"{agent_id}/{topic}", rel=f"04-LEARNINGS/by-topic/{topic}.md")
        return {"ok": True, "topic": topic, "agent_id": agent_id}

    def record_discovery(
        self,
        *,
        title: str,
        body: str,
        tags: List[str] | None = None,
        agent_id: str | None = None,
        tick: int | None = None,
        rid: str | None = None,
    ) -> dict:
        """Wiki discovery page (ricerca / sintesi). `rid`: vedi record_lesson()."""
        self._ensure_dirs()
        slug = _slug(title)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        body = PIISanitizer.sanitize_text(str(body or "").strip())
        tags = list(tags or []) + ["discovered", "civitas"]
        path = self.root / "06-MEMORY" / "wiki" / "discovered" / f"{slug}.md"
        content = (
            f"---\ntags: [{', '.join(tags)}]\nupdated: {stamp}\n"
            f"agent_id: {agent_id or 'collective'}\nrid: {rid or ''}\n---\n\n"
            f"# {title}\n\n{body}\n\n"
            f"<!-- tick={tick} source=research rid={rid or ''} -->\n"
        )
        if path.exists():
            with path.open("a", encoding="utf-8") as f:
                f.write(f"\n## Update {stamp}\n\n{body}\n\n<!-- rid={rid or ''} -->\n")
        else:
            path.write_text(content, encoding="utf-8")
        self._upsert(
            f"{title}\n{body}",
            tags=["wiki", "discovered"] + tags,
            rid=rid,
            agent_id=agent_id,
            tick=tick,
        )
        self.stats["discoveries"] += 1
        rel = f"06-MEMORY/wiki/discovered/{slug}.md"
        self._touch_catalog(kind="discovery", title=title, rel=rel)
        return {"ok": True, "path": rel}

    def record_world_build(self, *, poi: str, meta: dict, tick: int | None = None) -> dict:
        header = (
            "---\ntags: [civitas, world, built]\n---\n\n"
            "# Edifici costruiti (città vivente)\n\n"
            "| tick | poi | source | note |\n|------|-----|--------|------|\n"
        )
        note = str(meta.get("description") or meta.get("thought") or "")[:120]
        source = str(meta.get("source") or meta.get("blueprint_id") or "")
        line = f"| {tick} | {poi} | {source} | {note} |\n"
        self._append("03-WORLD/built-pois.md", line, header_if_new=header)
        self._upsert(
            f"POI built: {poi} source={source} {note}",
            tags=["world", "poi", "built", _slug(poi)],
            tick=tick,
        )
        self.stats["world"] += 1
        return {"ok": True, "poi": poi}

    def _touch_catalog(self, *, kind: str, title: str, rel: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        header = (
            "---\ntags: [civitas, catalog, vault]\n---\n\n"
            "# Catalogo conoscenza vivente\n\n"
            "Indice di ciò che gli AGI-OS hanno cercato, imparato e salvato.\n\n"
            "| date | kind | title | path |\n|------|------|-------|------|\n"
        )
        line = f"| {stamp} | {kind} | {title} | [[{rel.replace('.md','')}]] |\n"
        self._append("00-META/KNOWLEDGE-CATALOG.md", line, header_if_new=header)
        self.stats["catalog"] += 1

    def snapshot(self) -> dict:
        return {"vault": str(self.root), "stats": dict(self.stats)}
