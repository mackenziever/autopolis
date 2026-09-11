"""Carica skill Markdown dal vault condiviso (per tutti gli agenti)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

# Default: vault/ relativo al release root
_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_VAULT = _ROOT / "vault" / "02-SKILLS"

EVENT_TO_SKILL = {
    "daily_reflection": "reflect-and-improve.md",
    "career_choice": "career-ladder.md",
    "study_focus": "study-mastery.md",
    "social_stance": "plaza-social.md",
    "exam_feedback": "exam-feedback.md",
    "build_choice": "build-city.md",
    "room_choice": "room-manage.md",
    "research_focus": "research-vault.md",
}


@lru_cache(maxsize=32)
def load_skill_text(filename: str, vault_skills: str | None = None) -> str:
    root = Path(vault_skills) if vault_skills else _DEFAULT_VAULT
    path = root / filename
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def skill_for_event(event: str, vault_skills: str | None = None) -> str:
    name = EVENT_TO_SKILL.get(event)
    if not name:
        return ""
    text = load_skill_text(name, vault_skills)
    # Cap prompt bloat
    if len(text) > 2500:
        return text[:2500] + "\n…"
    return text


def inject_skill(system_prompt: str, event: str, vault_skills: str | None = None) -> str:
    skill = skill_for_event(event, vault_skills)
    if not skill:
        return system_prompt
    return f"{system_prompt}\n\n--- SKILL ({event}) ---\n{skill}\n--- END SKILL ---"
