"""Prepared radar/DCA state persisted between cold prepare and warm capture."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from ti_radar.core import paths as core_paths

STATE_DIR = core_paths.PROJECT_ROOT / ".radar_state"


def profile_hash(profile: dict[str, Any]) -> str:
    """Stable hash for the exact profile state sent during prepare."""
    payload = json.dumps(profile, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def state_path(profile_name: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in profile_name)
    return STATE_DIR / f"{safe}_state.json"


def read_state(profile_name: str) -> dict[str, Any] | None:
    path = state_path(profile_name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(profile_name: str, state: dict[str, Any]) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = state_path(profile_name)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def prepared_state(
    *,
    profile_name: str,
    profile: dict[str, Any],
    frames: int,
    studio_pid: int | None,
    rstd_ok: bool,
) -> dict[str, Any]:
    return {
        "profile": profile_name,
        "profile_hash": profile_hash(profile),
        "frames": int(frames),
        "studio_pid": studio_pid,
        "rstd_ok": bool(rstd_ok),
        "firmware_loaded": True,
        "radar_configured": True,
        "dca_eth_initialized": True,
        "prepared_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def validate_prepared_state(
    *,
    state: dict[str, Any] | None,
    profile_name: str,
    profile: dict[str, Any],
    frames: int,
) -> list[str]:
    """Return failure reasons for using a warm capture state."""
    if state is None:
        return [f"state file missing for profile {profile_name!r}; run `ti-radar studio prepare --profile {profile_name}`"]

    failures: list[str] = []
    if state.get("profile") != profile_name:
        failures.append("state profile mismatch: %r != %r" % (state.get("profile"), profile_name))
    if state.get("profile_hash") != profile_hash(profile):
        failures.append("profile hash mismatch; run cold prepare again")
    if int(state.get("frames", -1)) != int(frames):
        failures.append("prepared frames=%s but requested frames=%s; run prepare with the same frame count" % (state.get("frames"), frames))
    for key in ("rstd_ok", "firmware_loaded", "radar_configured", "dca_eth_initialized"):
        if not state.get(key):
            failures.append("state flag %s is not true" % key)
    return failures
