from __future__ import annotations

from pathlib import Path
from typing import Any

from nouse.daemon.system_events import enqueue_system_event, request_wake
from nouse.ingress.allowlist import (
    INGRESS_ALLOWLIST_PATH,
    approve_pairing,
    is_allowed,
    list_allowed,
    list_pending,
    request_pairing,
)
from nouse.session import ensure_session


def _sanitize_token(raw: str | None, *, default: str, max_len: int = 64) -> str:
    text = "".join(ch for ch in str(raw or "").strip() if ch.isalnum() or ch in {"-", "_"})
    return text[:max_len] if text else default


def _channel_key(channel: str) -> str:
    safe_channel = _sanitize_token(channel, default="default")
    return f"clawbot:{safe_channel}"


def _session_id(channel: str, actor_id: str) -> str:
    ch = _sanitize_token(channel, default="default", max_len=24)
    actor = _sanitize_token(actor_id, default="unknown", max_len=24)
    return _sanitize_token(f"clawbot_{ch}_{actor}", default="clawbot_main", max_len=64)


def get_clawbot_allowlist(channel: str, *, path: Path = INGRESS_ALLOWLIST_PATH) -> dict[str, Any]:
    key = _channel_key(channel)
    return {
        "channel": _sanitize_token(channel, default="default"),
        "allowlist_channel": key,
        "allowed": list_allowed(key, path=path),
        "pending": list_pending(key, path=path),
    }


def approve_clawbot_pairing(
    channel: str,
    code: str,
    *,
    path: Path = INGRESS_ALLOWLIST_PATH,
) -> dict[str, Any] | None:
    key = _channel_key(channel)
    approved = approve_pairing(key, code, path=path)
    if approved is None:
        return None
    return {
        "channel": _sanitize_token(channel, default="default"),
        "allowlist_channel": key,
        "actor_id": approved.get("actor_id"),
        "code": approved.get("code"),
    }


def ingest_clawbot_event(
    *,
    text: str,
    channel: str = "default",
    actor_id: str = "",
    source: str = "clawbot",
    mode: str = "now",
    strict_pairing: bool = True,
    context_key: str = "",
    allowlist_path: Path = INGRESS_ALLOWLIST_PATH,
) -> dict[str, Any]:
    clean_text = str(text or "").strip()
    if not clean_text:
        return {"ok": False, "accepted": False, "error": "text required"}

    safe_channel = _sanitize_token(channel, default="default")
    safe_actor = _sanitize_token(actor_id, default="unknown")
    safe_source = str(source or "clawbot").strip()[:120] or "clawbot"
    safe_mode = str(mode or "now").strip().lower()
    if safe_mode not in {"now", "next-heartbeat"}:
        safe_mode = "now"

    allowlist_channel = _channel_key(safe_channel)

    # Pairing command from client.
    if clean_text.lower().startswith("/pair "):
        code = clean_text.split(" ", 1)[1].strip().upper()
        approved = approve_pairing(allowlist_channel, code, path=allowlist_path)
        return {
            "ok": approved is not None,
            "accepted": approved is not None,
            "pairing_approved": approved is not None,
            "channel": safe_channel,
            "actor_id": safe_actor,
            "allowlist_channel": allowlist_channel,
            "code": code,
        }

    if strict_pairing and not is_allowed(allowlist_channel, safe_actor, path=allowlist_path):
        pairing = request_pairing(allowlist_channel, safe_actor, path=allowlist_path)
        return {
            "ok": False,
            "accepted": False,
            "requires_pairing": True,
            "pairing_code": pairing["code"],
            "channel": safe_channel,
            "actor_id": safe_actor,
            "allowlist_channel": allowlist_channel,
        }

    sid = _session_id(safe_channel, safe_actor)
    ensure_session(
        sid,
        lane="ingress",
        source=safe_source,
        meta={
            "channel": safe_channel,
            "actor_id": safe_actor,
            "source": safe_source,
            "ingress": "clawbot",
        },
    )
    queued = enqueue_system_event(
        clean_text,
        session_id=sid,
        source=safe_source,
        context_key=context_key,
    )
    wake_requested = safe_mode == "now"
    if wake_requested:
        request_wake(
            reason=f"clawbot:{safe_channel}",
            session_id=sid,
            source=safe_source,
        )
    return {
        "ok": True,
        "accepted": True,
        "queued": queued,
        "wake_requested": wake_requested,
        "mode": safe_mode,
        "session_id": sid,
        "channel": safe_channel,
        "actor_id": safe_actor,
        "allowlist_channel": allowlist_channel,
    }
