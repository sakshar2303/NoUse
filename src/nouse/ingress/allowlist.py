from __future__ import annotations

import json
import secrets
import string
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INGRESS_ALLOWLIST_PATH = Path.home() / ".local" / "share" / "b76" / "ingress_allowlist.json"
_LOCK = threading.Lock()
_PAIR_ALPHABET = string.ascii_uppercase + string.digits


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blank_state() -> dict[str, Any]:
    return {"channels": {}, "updated_at": _now_iso()}


def _normalize_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _blank_state()
    channels = raw.get("channels")
    out = _blank_state()
    if isinstance(channels, dict):
        for channel, row in channels.items():
            if not isinstance(row, dict):
                continue
            allowed = row.get("allowed")
            pending = row.get("pending")
            out["channels"][str(channel)] = {
                "allowed": [str(x) for x in (allowed or []) if str(x)],
                "pending": pending if isinstance(pending, dict) else {},
            }
    out["updated_at"] = str(raw.get("updated_at") or out["updated_at"])
    return out


def _load(path: Path = INGRESS_ALLOWLIST_PATH) -> dict[str, Any]:
    if not path.exists():
        return _blank_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _blank_state()
    return _normalize_state(raw)


def _save(state: dict[str, Any], path: Path = INGRESS_ALLOWLIST_PATH) -> dict[str, Any]:
    out = _normalize_state(state)
    out["updated_at"] = _now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _channel_row(state: dict[str, Any], channel: str) -> dict[str, Any]:
    channels = state.setdefault("channels", {})
    row = channels.setdefault(str(channel), {"allowed": [], "pending": {}})
    row.setdefault("allowed", [])
    row.setdefault("pending", {})
    channels[str(channel)] = row
    return row


def is_allowed(channel: str, actor_id: str, *, path: Path = INGRESS_ALLOWLIST_PATH) -> bool:
    actor = str(actor_id or "").strip()
    if not actor:
        return False
    with _LOCK:
        state = _load(path)
    row = _channel_row(state, channel)
    return actor in set(str(x) for x in row.get("allowed", []))


def add_allowed_actor(channel: str, actor_id: str, *, path: Path = INGRESS_ALLOWLIST_PATH) -> bool:
    actor = str(actor_id or "").strip()
    if not actor:
        return False
    with _LOCK:
        state = _load(path)
        row = _channel_row(state, channel)
        allowed = [str(x) for x in row.get("allowed", []) if str(x)]
        if actor not in allowed:
            allowed.append(actor)
        row["allowed"] = allowed
        # Remove stale pairing requests for actor.
        pending = row.get("pending") or {}
        remove_codes = [code for code, item in pending.items() if str((item or {}).get("actor_id") or "") == actor]
        for code in remove_codes:
            pending.pop(code, None)
        row["pending"] = pending
        _save(state, path)
    return True


def remove_allowed_actor(channel: str, actor_id: str, *, path: Path = INGRESS_ALLOWLIST_PATH) -> bool:
    actor = str(actor_id or "").strip()
    if not actor:
        return False
    changed = False
    with _LOCK:
        state = _load(path)
        row = _channel_row(state, channel)
        allowed = [str(x) for x in row.get("allowed", []) if str(x)]
        if actor in allowed:
            allowed = [x for x in allowed if x != actor]
            changed = True
        row["allowed"] = allowed
        if changed:
            _save(state, path)
    return changed


def _new_pairing_code(length: int = 6) -> str:
    return "".join(secrets.choice(_PAIR_ALPHABET) for _ in range(max(4, length)))


def request_pairing(channel: str, actor_id: str, *, path: Path = INGRESS_ALLOWLIST_PATH) -> dict[str, Any]:
    actor = str(actor_id or "").strip()
    if not actor:
        raise ValueError("actor_id required")
    with _LOCK:
        state = _load(path)
        row = _channel_row(state, channel)
        pending = row.get("pending") or {}
        for code, item in pending.items():
            if str((item or {}).get("actor_id") or "") == actor:
                return {
                    "channel": channel,
                    "actor_id": actor,
                    "code": str(code),
                    "created_at": str((item or {}).get("created_at") or _now_iso()),
                    "existing": True,
                }
        code = _new_pairing_code()
        pending[code] = {"actor_id": actor, "created_at": _now_iso()}
        row["pending"] = pending
        _save(state, path)
    return {
        "channel": channel,
        "actor_id": actor,
        "code": code,
        "created_at": _now_iso(),
        "existing": False,
    }


def approve_pairing(
    channel: str,
    code: str,
    *,
    path: Path = INGRESS_ALLOWLIST_PATH,
) -> dict[str, Any] | None:
    wanted = str(code or "").strip().upper()
    if not wanted:
        return None
    with _LOCK:
        state = _load(path)
        row = _channel_row(state, channel)
        pending = row.get("pending") or {}
        item = pending.pop(wanted, None)
        if not isinstance(item, dict):
            return None
        actor = str(item.get("actor_id") or "").strip()
        if not actor:
            return None
        allowed = [str(x) for x in row.get("allowed", []) if str(x)]
        if actor not in allowed:
            allowed.append(actor)
        row["allowed"] = allowed
        row["pending"] = pending
        _save(state, path)
    return {"channel": channel, "actor_id": actor, "code": wanted}


def list_allowed(channel: str, *, path: Path = INGRESS_ALLOWLIST_PATH) -> list[str]:
    with _LOCK:
        state = _load(path)
    row = _channel_row(state, channel)
    values = [str(x) for x in row.get("allowed", []) if str(x)]
    values.sort()
    return values


def list_pending(channel: str, *, path: Path = INGRESS_ALLOWLIST_PATH) -> list[dict[str, str]]:
    with _LOCK:
        state = _load(path)
    row = _channel_row(state, channel)
    pending = row.get("pending") or {}
    rows = []
    for code, item in pending.items():
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "code": str(code),
                "actor_id": str(item.get("actor_id") or ""),
                "created_at": str(item.get("created_at") or ""),
            }
        )
    rows.sort(key=lambda r: (r.get("created_at") or "", r.get("code") or ""))
    return rows
