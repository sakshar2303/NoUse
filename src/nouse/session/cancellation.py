from __future__ import annotations

from pathlib import Path
from typing import Any

from nouse.session.state import (
    SESSION_STATE_PATH,
    finish_run,
    get_session,
)
from nouse.session.writer import record_session_event


def cancel_active_run(
    session_id: str,
    *,
    reason: str = "manual_cancel",
    actor: str = "human",
    path: Path = SESSION_STATE_PATH,
) -> dict[str, Any] | None:
    session = get_session(session_id, path=path)
    if not session:
        return None
    run_id = str(session.get("active_run_id") or "").strip()
    if not run_id:
        return None
    row = finish_run(
        run_id,
        status="cancelled",
        error=f"cancelled by {actor}: {reason}",
        metrics={"cancel_actor": actor, "cancel_reason": reason},
        path=path,
    )
    if row:
        record_session_event(
            session_id,
            "run.cancelled",
            run_id=run_id,
            payload={"reason": reason, "actor": actor},
        )
    return row
