from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = Path.home() / ".local" / "share" / "nouse" / "model_capabilities.json"
_LOCK = threading.Lock()

_TOOLS_UNSUPPORTED_MARKERS = (
    "does not support tools",
    "tool calling not supported",
    "tools are not supported",
    "unsupported parameter: tools",
    "tool_calls is not supported",
    "function calling is not supported",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "version": 1,
        "updated_at": _now_iso(),
        "models": {},
    }
    if not isinstance(raw, dict):
        return base
    models = raw.get("models")
    norm_models: dict[str, dict[str, Any]] = {}
    if isinstance(models, dict):
        for key, row in models.items():
            model = str(key or "").strip()
            if not model or not isinstance(row, dict):
                continue
            supports_tools = row.get("supports_tools")
            if supports_tools is None:
                continue
            norm_models[model] = {
                "supports_tools": bool(supports_tools),
                "updated_at": str(row.get("updated_at") or _now_iso()),
                "reason": str(row.get("reason") or "").strip(),
            }
    base["version"] = int(raw.get("version", 1) or 1)
    base["updated_at"] = str(raw.get("updated_at") or _now_iso())
    base["models"] = norm_models
    return base


def load_capabilities(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return _normalize_state(None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _normalize_state(None)
    return _normalize_state(raw)


def save_capabilities(state: dict[str, Any], path: Path = STATE_PATH) -> dict[str, Any]:
    out = _normalize_state(state)
    out["updated_at"] = _now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def is_tools_unsupported_error(error: Exception | str) -> bool:
    text = str(error or "").lower()
    return any(marker in text for marker in _TOOLS_UNSUPPORTED_MARKERS)


def mark_model_tools_unsupported(
    model: str,
    *,
    reason: str = "",
    path: Path = STATE_PATH,
) -> None:
    name = str(model or "").strip()
    if not name:
        return
    with _LOCK:
        state = load_capabilities(path)
        models = state.setdefault("models", {})
        models[name] = {
            "supports_tools": False,
            "updated_at": _now_iso(),
            "reason": str(reason or "").strip()[:500],
        }
        save_capabilities(state, path)


def mark_model_tools_supported(model: str, *, path: Path = STATE_PATH) -> None:
    name = str(model or "").strip()
    if not name:
        return
    with _LOCK:
        state = load_capabilities(path)
        models = state.setdefault("models", {})
        models[name] = {
            "supports_tools": True,
            "updated_at": _now_iso(),
            "reason": "",
        }
        save_capabilities(state, path)


def filter_tool_capable_models(
    candidates: list[str],
    *,
    path: Path = STATE_PATH,
) -> tuple[list[str], list[str]]:
    dedup: list[str] = []
    seen = set()
    for item in candidates or []:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        dedup.append(name)
    if not dedup:
        return [], []
    with _LOCK:
        state = load_capabilities(path)
    known = (state.get("models") or {}) if isinstance(state, dict) else {}
    allowed: list[str] = []
    skipped: list[str] = []
    for model in dedup:
        row = known.get(model)
        if isinstance(row, dict) and row.get("supports_tools") is False:
            skipped.append(model)
        else:
            allowed.append(model)
    return allowed, skipped
