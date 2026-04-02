from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USAGE_LOG_PATH = Path.home() / ".local" / "share" / "b76" / "usage_log.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_pricing() -> dict[str, dict[str, float]]:
    raw = (os.getenv("NOUSE_USAGE_PRICING_JSON") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for model, row in parsed.items():
        if not isinstance(row, dict):
            continue
        try:
            prompt = max(0.0, float(row.get("prompt_per_1k", 0.0) or 0.0))
            completion = max(0.0, float(row.get("completion_per_1k", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
        out[str(model)] = {
            "prompt_per_1k": prompt,
            "completion_per_1k": completion,
        }
    return out


def estimate_cost_usd(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    pricing = _parse_pricing().get(str(model), {})
    p_rate = float(pricing.get("prompt_per_1k", 0.0))
    c_rate = float(pricing.get("completion_per_1k", 0.0))
    if p_rate <= 0 and c_rate <= 0:
        return 0.0
    return (max(0, int(prompt_tokens)) / 1000.0) * p_rate + (
        max(0, int(completion_tokens)) / 1000.0
    ) * c_rate


def record_usage(row: dict[str, Any], path: Path = USAGE_LOG_PATH) -> dict[str, Any]:
    out = {
        "ts": str(row.get("ts") or _now_iso()),
        "session_id": str(row.get("session_id") or "").strip() or "main",
        "run_id": str(row.get("run_id") or "").strip() or None,
        "workload": str(row.get("workload") or "").strip() or "unknown",
        "provider": str(row.get("provider") or "").strip() or "unknown",
        "model": str(row.get("model") or "").strip() or "unknown",
        "status": str(row.get("status") or "").strip() or "unknown",
        "latency_ms": max(0, int(row.get("latency_ms", 0) or 0)),
        "prompt_tokens": max(0, int(row.get("prompt_tokens", 0) or 0)),
        "completion_tokens": max(0, int(row.get("completion_tokens", 0) or 0)),
        "total_tokens": max(0, int(row.get("total_tokens", 0) or 0)),
        "cost_usd": max(0.0, float(row.get("cost_usd", 0.0) or 0.0)),
        "error": str(row.get("error") or "")[:1000],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return out


def list_usage(
    *,
    limit: int = 200,
    session_id: str | None = None,
    workload: str | None = None,
    model: str | None = None,
    status: str | None = None,
    path: Path = USAGE_LOG_PATH,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    safe_limit = max(1, min(int(limit), 10000))
    wanted_session = str(session_id or "").strip()
    wanted_workload = str(workload or "").strip()
    wanted_model = str(model or "").strip()
    wanted_status = str(status or "").strip().lower()
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            if wanted_session and str(row.get("session_id") or "") != wanted_session:
                continue
            if wanted_workload and str(row.get("workload") or "") != wanted_workload:
                continue
            if wanted_model and str(row.get("model") or "") != wanted_model:
                continue
            if wanted_status and str(row.get("status") or "").lower() != wanted_status:
                continue
            rows.append(row)
    rows.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
    return rows[:safe_limit]


def usage_summary(
    *,
    limit: int = 1000,
    path: Path = USAGE_LOG_PATH,
) -> dict[str, Any]:
    rows = list_usage(limit=limit, path=path)
    total_cost = 0.0
    total_tokens = 0
    total_prompt = 0
    total_completion = 0
    failed = 0
    by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        model = str(row.get("model") or "unknown")
        status = str(row.get("status") or "")
        prompt = max(0, int(row.get("prompt_tokens", 0) or 0))
        completion = max(0, int(row.get("completion_tokens", 0) or 0))
        total = max(0, int(row.get("total_tokens", 0) or (prompt + completion)))
        cost = max(0.0, float(row.get("cost_usd", 0.0) or 0.0))
        total_prompt += prompt
        total_completion += completion
        total_tokens += total
        total_cost += cost
        if status == "failed":
            failed += 1
        bucket = by_model.setdefault(
            model,
            {
                "calls": 0,
                "failed": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "avg_latency_ms": 0,
            },
        )
        bucket["calls"] += 1
        bucket["total_tokens"] += total
        bucket["cost_usd"] += cost
        if status == "failed":
            bucket["failed"] += 1
        lat = int(row.get("latency_ms", 0) or 0)
        # Streaming mean without keeping all values.
        prev_calls = max(1, bucket["calls"])
        old_avg = int(bucket.get("avg_latency_ms", 0) or 0)
        bucket["avg_latency_ms"] = int(((old_avg * (prev_calls - 1)) + lat) / prev_calls)

    models = [
        {"model": model, **bucket}
        for model, bucket in by_model.items()
    ]
    models.sort(key=lambda r: (float(r.get("cost_usd", 0.0)), int(r.get("calls", 0))), reverse=True)
    return {
        "rows": len(rows),
        "failed": failed,
        "total_tokens": total_tokens,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "cost_usd": round(total_cost, 6),
        "by_model": models,
    }
