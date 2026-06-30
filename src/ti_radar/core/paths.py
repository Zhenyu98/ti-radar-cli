"""Shared project paths for ti-radar."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SESSIONS = PROJECT_ROOT / "sessions"


def session_roots() -> tuple[Path, ...]:
    return (SESSIONS,)
