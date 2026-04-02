from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSION_EVENTS_PATH = Path.home() / ".local" / "share" / "b76" / "session_events.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_session_event(
    session_id: str,
    event: str,
    *,
    run_id: str | None = None,
    payload: dict[str, Any] | None = None,
    path: Path = SESSION_EVENTS_PATH,
) -> None:
    row = {
        "ts": _now_iso(),
        "session_id": str(session_id or "").strip() or "main",
        "run_id": str(run_id or "").strip() or None,
        "event": str(event or "").strip() or "unknown",
        "payload": dict(payload or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
