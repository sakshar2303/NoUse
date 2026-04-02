from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STATE_PATH = Path.home() / ".local" / "share" / "nouse" / "model_router.json"
_LOCK = threading.Lock()


def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw = (os.getenv(name, str(default)) or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = (os.getenv(name, str(default)) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


_HALF_LIFE_HOURS = _env_float("NOUSE_MODEL_ROUTER_HALF_LIFE_HOURS", 72.0, minimum=1.0)
_MAX_EFFECTIVE_ATTEMPTS = _env_int("NOUSE_MODEL_ROUTER_MAX_EFFECTIVE_ATTEMPTS", 120, minimum=8)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    if not _STATE_PATH.exists():
        return {"workloads": {}}
    try:
        raw = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"workloads": {}}
    if not isinstance(raw, dict):
        return {"workloads": {}}
    raw.setdefault("workloads", {})
    return raw


def _save_state(state: dict[str, Any]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso_ts(raw: Any) -> float | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()


def _effective_counters(now_ts: float, row: dict[str, Any]) -> tuple[float, float, float, float]:
    success = max(0.0, float(row.get("success", 0) or 0))
    failure = max(0.0, float(row.get("failure", 0) or 0))
    timeout = max(0.0, float(row.get("timeout", 0) or 0))
    quality_sum = max(0.0, float(row.get("quality_sum", 0.0) or 0.0))
    quality_count = max(0.0, float(row.get("quality_count", 0.0) or 0.0))

    updated_ts = _parse_iso_ts(row.get("updated"))
    if updated_ts is not None and updated_ts < now_ts:
        age_hours = (now_ts - updated_ts) / 3600.0
        decay = 0.5 ** (age_hours / _HALF_LIFE_HOURS)
        success *= decay
        failure *= decay
        timeout *= decay
        quality_sum *= decay
        quality_count *= decay

    total = success + failure + timeout
    if total > _MAX_EFFECTIVE_ATTEMPTS:
        scale = _MAX_EFFECTIVE_ATTEMPTS / max(1e-9, total)
        success *= scale
        failure *= scale
        timeout *= scale

    quality_avg = (quality_sum / quality_count) if quality_count > 1e-9 else 0.0
    quality_avg = max(0.0, min(1.0, quality_avg))
    return success, failure, timeout, quality_avg


def _score(now_ts: float, row: dict[str, Any]) -> float:
    success, failure, timeout, quality_avg = _effective_counters(now_ts, row)
    attempts = success + failure + timeout
    fail_rate = (failure + timeout * 1.4) / max(1.0, attempts + 1.0)
    cooldown_until = float(row.get("cooldown_until", 0.0) or 0.0)
    cooldown_penalty = 0.0
    if cooldown_until > now_ts:
        cooldown_penalty = min(5.0, 1.0 + (cooldown_until - now_ts) / 600.0)
    # Favor models with explicit successes, but only lightly.
    success_bonus = min(0.3, success / 60.0)
    quality_bonus = min(0.2, quality_avg * 0.2)
    return fail_rate + cooldown_penalty - success_bonus - quality_bonus


def decay_router_state(
    *,
    workload: str | None = None,
    factor: float = 0.15,
    clear_cooldowns: bool = True,
) -> dict[str, int]:
    """
    Minska historiska modellräknare för att undvika att gamla felregimer
    (t.ex. tidigare timeout-konfigurationer) styr routing för länge.
    """
    safe_factor = max(0.0, min(1.0, float(factor)))
    touched_workloads = 0
    touched_models = 0
    with _LOCK:
        state = _load_state()
        workloads = state.get("workloads") or {}
        names = [workload] if workload else list(workloads.keys())
        for name in names:
            rows = workloads.get(name)
            if not isinstance(rows, dict):
                continue
            touched_workloads += 1
            for model, row in rows.items():
                if not isinstance(row, dict):
                    continue
                touched_models += 1
                row["success"] = int(round(max(0.0, float(row.get("success", 0) or 0)) * safe_factor))
                row["failure"] = int(round(max(0.0, float(row.get("failure", 0) or 0)) * safe_factor))
                row["timeout"] = int(round(max(0.0, float(row.get("timeout", 0) or 0)) * safe_factor))
                row["quality_sum"] = max(0.0, float(row.get("quality_sum", 0.0) or 0.0) * safe_factor)
                row["quality_count"] = max(0.0, float(row.get("quality_count", 0.0) or 0.0) * safe_factor)
                row["consecutive_timeouts"] = 0
                if clear_cooldowns:
                    row["cooldown_until"] = 0.0
                row["updated"] = _now_iso()
                rows[model] = row
            workloads[name] = rows
        state["workloads"] = workloads
        _save_state(state)
    return {"workloads": touched_workloads, "models": touched_models}


def order_models_for_workload(workload: str, candidates: list[str]) -> list[str]:
    """
    Returnerar kandidater sorterade efter historisk tillförlitlighet för workload.
    """
    dedup: list[str] = []
    seen = set()
    for c in candidates:
        model = (c or "").strip()
        if not model or model in seen:
            continue
        seen.add(model)
        dedup.append(model)
    if len(dedup) <= 1:
        return dedup

    with _LOCK:
        state = _load_state()
        rows = (state.get("workloads") or {}).get(workload) or {}
        now_ts = time.time()
        ranked = sorted(
            dedup,
            key=lambda model: (_score(now_ts, rows.get(model) or {}), dedup.index(model)),
        )
    return ranked


def record_model_result(
    workload: str,
    model: str,
    *,
    success: bool,
    timeout: bool = False,
    quality: float | None = None,
) -> None:
    if not workload or not model:
        return

    with _LOCK:
        state = _load_state()
        workloads = state.setdefault("workloads", {})
        wrk = workloads.setdefault(workload, {})
        row = wrk.setdefault(
            model,
            {
                "success": 0,
                "failure": 0,
                "timeout": 0,
                "consecutive_timeouts": 0,
                "cooldown_until": 0.0,
                "quality_sum": 0.0,
                "quality_count": 0.0,
                "updated": "",
            },
        )

        if success:
            row["success"] = int(row.get("success", 0) or 0) + 1
            row["consecutive_timeouts"] = max(
                0, int(row.get("consecutive_timeouts", 0) or 0) - 1
            )
            if quality is not None:
                q = max(0.0, min(1.0, float(quality)))
                row["quality_sum"] = float(row.get("quality_sum", 0.0) or 0.0) + q
                row["quality_count"] = float(row.get("quality_count", 0.0) or 0.0) + 1.0
        else:
            row["failure"] = int(row.get("failure", 0) or 0) + 1
            if timeout:
                row["timeout"] = int(row.get("timeout", 0) or 0) + 1
                cto = int(row.get("consecutive_timeouts", 0) or 0) + 1
                row["consecutive_timeouts"] = cto
                if cto >= 2:
                    delay = min(1800, 60 * (2 ** min(cto - 2, 5)))
                    row["cooldown_until"] = time.time() + delay
            else:
                row["consecutive_timeouts"] = 0

        row["updated"] = _now_iso()
        _save_state(state)


def router_status(
    *,
    workload: str | None = None,
) -> dict[str, Any]:
    with _LOCK:
        state = _load_state()
    workloads = state.get("workloads") or {}
    now_ts = time.time()
    out: dict[str, Any] = {"updated_at": _now_iso(), "workloads": {}}
    names = [workload] if workload else list(workloads.keys())
    for name in names:
        rows = workloads.get(name)
        if not isinstance(rows, dict):
            continue
        entries: list[dict[str, Any]] = []
        for model, row in rows.items():
            if not isinstance(row, dict):
                continue
            score = _score(now_ts, row)
            entries.append(
                {
                    "model": str(model),
                    "score": round(float(score), 6),
                    "success": int(row.get("success", 0) or 0),
                    "failure": int(row.get("failure", 0) or 0),
                    "timeout": int(row.get("timeout", 0) or 0),
                    "consecutive_timeouts": int(row.get("consecutive_timeouts", 0) or 0),
                    "cooldown_until": float(row.get("cooldown_until", 0.0) or 0.0),
                    "quality_avg": round(
                        max(
                            0.0,
                            min(
                                1.0,
                                (
                                    float(row.get("quality_sum", 0.0) or 0.0)
                                    / max(1.0, float(row.get("quality_count", 0.0) or 0.0))
                                ),
                            ),
                        ),
                        6,
                    ),
                    "updated": str(row.get("updated") or ""),
                }
            )
        entries.sort(key=lambda r: (float(r.get("score", 99.0)), str(r.get("model", ""))))
        out["workloads"][str(name)] = entries
    return out
