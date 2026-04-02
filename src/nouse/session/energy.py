from __future__ import annotations

from pathlib import Path
from typing import Any

from nouse.session.state import (
    SESSION_STATE_PATH,
    ensure_session,
    get_session,
    set_session_energy,
)
from nouse.session.writer import record_session_event


def set_energy(
    session_id: str,
    energy: float,
    *,
    source: str = "manual",
    path: Path = SESSION_STATE_PATH,
) -> dict[str, Any]:
    ensure_session(session_id, source=source, path=path)
    row = set_session_energy(session_id, energy, path=path)
    record_session_event(
        session_id,
        "energy.set",
        payload={"energy": float(row.get("energy", 0.5)), "source": source},
    )
    return row


def get_energy(session_id: str, *, path: Path = SESSION_STATE_PATH) -> float | None:
    row = get_session(session_id, path=path)
    if not row:
        return None
    try:
        return float(row.get("energy"))
    except (TypeError, ValueError):
        return None
