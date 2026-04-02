from __future__ import annotations

import asyncio
import os
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

_MAX_EVENTS = max(20, int(os.getenv("NOUSE_SYSTEM_EVENT_MAX_QUEUE", "200")))
_MAX_WAKE_REASONS = max(20, int(os.getenv("NOUSE_WAKE_REASON_MAX_QUEUE", "200")))

_LOCK = threading.Lock()
_EVENTS: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_WAKE_REASONS: deque[dict[str, Any]] = deque(maxlen=_MAX_WAKE_REASONS)
_LAST_TEXT_BY_SESSION: dict[str, str] = {}
_WAKE_EVENT: asyncio.Event | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_session_id(session_id: str | None) -> str:
    safe = "".join(
        ch for ch in str(session_id or "").strip() if ch.isalnum() or ch in {"-", "_"}
    )
    return safe[:64] if safe else "main"


def _clean_context_key(context_key: str | None) -> str:
    raw = str(context_key or "").strip().lower()
    return raw[:120] if raw else ""


def bind_wake_event(event: asyncio.Event | None) -> None:
    """Bind en asyncio.Event som request_wake() kan trigga."""
    global _WAKE_EVENT
    with _LOCK:
        _WAKE_EVENT = event


def enqueue_system_event(
    text: str,
    *,
    session_id: str = "main",
    source: str = "api",
    context_key: str = "",
) -> bool:
    clean_text = str(text or "").strip()
    if not clean_text:
        return False
    sid = _clean_session_id(session_id)
    clean_source = str(source or "api").strip()[:120] or "api"
    clean_context = _clean_context_key(context_key)
    with _LOCK:
        if _LAST_TEXT_BY_SESSION.get(sid) == clean_text:
            return False
        _LAST_TEXT_BY_SESSION[sid] = clean_text
        _EVENTS.append(
            {
                "ts": _now_iso(),
                "session_id": sid,
                "source": clean_source,
                "context_key": clean_context or None,
                "text": clean_text,
            }
        )
    return True


def drain_system_event_entries(*, limit: int = 50, session_id: str = "") -> list[dict[str, Any]]:
    safe_limit = max(1, int(limit))
    wanted_sid = _clean_session_id(session_id) if str(session_id or "").strip() else ""
    out: list[dict[str, Any]] = []
    with _LOCK:
        if not _EVENTS:
            return out
        if not wanted_sid:
            while _EVENTS and len(out) < safe_limit:
                out.append(dict(_EVENTS.popleft()))
            if not _EVENTS:
                _LAST_TEXT_BY_SESSION.clear()
            return out

        kept: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
        while _EVENTS:
            row = _EVENTS.popleft()
            if (
                len(out) < safe_limit
                and str(row.get("session_id") or "") == wanted_sid
            ):
                out.append(dict(row))
                continue
            kept.append(row)
        _EVENTS.extend(kept)
        if out and not any(str(r.get("session_id") or "") == wanted_sid for r in _EVENTS):
            _LAST_TEXT_BY_SESSION.pop(wanted_sid, None)
    return out


def peek_system_event_entries(*, limit: int = 50, session_id: str = "") -> list[dict[str, Any]]:
    safe_limit = max(1, int(limit))
    wanted_sid = _clean_session_id(session_id) if str(session_id or "").strip() else ""
    with _LOCK:
        rows = list(_EVENTS)
    if wanted_sid:
        rows = [r for r in rows if str(r.get("session_id") or "") == wanted_sid]
    return [dict(r) for r in rows[:safe_limit]]


def system_event_stats() -> dict[str, Any]:
    with _LOCK:
        rows = list(_EVENTS)
    by_session: dict[str, int] = {}
    for row in rows:
        sid = str(row.get("session_id") or "main")
        by_session[sid] = by_session.get(sid, 0) + 1
    return {
        "pending_total": len(rows),
        "by_session": by_session,
        "queue_max": _MAX_EVENTS,
    }


def request_wake(
    *,
    reason: str = "manual",
    session_id: str = "main",
    source: str = "api",
) -> None:
    clean_reason = str(reason or "manual").strip()[:120] or "manual"
    sid = _clean_session_id(session_id)
    src = str(source or "api").strip()[:120] or "api"
    event: asyncio.Event | None = None
    with _LOCK:
        _WAKE_REASONS.append(
            {
                "ts": _now_iso(),
                "reason": clean_reason,
                "session_id": sid,
                "source": src,
            }
        )
        event = _WAKE_EVENT
    if event is not None:
        event.set()


def consume_wake_reasons(*, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, int(limit))
    out: list[dict[str, Any]] = []
    with _LOCK:
        while _WAKE_REASONS and len(out) < safe_limit:
            out.append(dict(_WAKE_REASONS.popleft()))
    return out


def peek_wake_reasons(*, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, int(limit))
    with _LOCK:
        rows = list(_WAKE_REASONS)[:safe_limit]
    return [dict(r) for r in rows]


def reset_system_event_state_for_test() -> None:
    global _WAKE_EVENT
    with _LOCK:
        _EVENTS.clear()
        _WAKE_REASONS.clear()
        _LAST_TEXT_BY_SESSION.clear()
        _WAKE_EVENT = None
