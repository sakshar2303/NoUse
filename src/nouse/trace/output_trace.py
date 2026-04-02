from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_WRITE_LOCK = threading.Lock()

_ASSUMPTION_HINTS = (
    "if ",
    " om ",
    "assuming",
    "assume",
    "antar",
    "antag",
    "förutsätt",
    "requires",
    "kräver",
)


def _trace_root() -> Path:
    custom = (os.getenv("NOUSE_TRACE_DIR") or "").strip()
    if custom:
        return Path(custom)
    return Path.home() / ".local" / "share" / "nouse" / "trace"


def _events_dir() -> Path:
    out = _trace_root() / "events"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _today_events_file() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _events_dir() / f"{stamp}.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(value: str, max_chars: int = 1200) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "…"


def new_trace_id(prefix: str = "trc") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{ts}_{uuid.uuid4().hex[:10]}"


def derive_assumptions(text: str, max_items: int = 8) -> list[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    parts = [p.strip() for p in re.split(r"[.!?\n]+", cleaned) if p.strip()]
    out: list[str] = []
    for part in parts:
        low = f" {part.lower()} "
        if any(h in low for h in _ASSUMPTION_HINTS):
            out.append(_clip(part, 220))
        if len(out) >= max_items:
            break
    return out


def build_attack_plan(text: str) -> dict[str, Any]:
    cleaned = " ".join((text or "").split())
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", cleaned) if p.strip()]
    questions: list[str] = []
    claims: list[str] = []
    assumptions: list[str] = []

    for part in parts:
        p = _clip(part, 280)
        low = f" {part.lower()} "
        if "?" in part:
            questions.append(p)
        elif any(h in low for h in _ASSUMPTION_HINTS):
            assumptions.append(p)
        else:
            claims.append(p)

    return {
        "questions": questions,
        "claims": claims,
        "assumptions": assumptions,
        "steps": [
            "normalize_input",
            "classify_question_claim_assumption",
            "collect_graph_context",
            "run_model_and_tools",
            "emit_output_with_evidence",
            "persist_trace",
        ],
    }


def record_event(
    trace_id: str,
    event: str,
    *,
    endpoint: str | None = None,
    model: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "ts": _now_iso(),
        "trace_id": trace_id,
        "event": event,
    }
    if endpoint:
        entry["endpoint"] = endpoint
    if model:
        entry["model"] = model
    if payload is not None:
        entry["payload"] = payload

    line = json.dumps(entry, ensure_ascii=False)
    with _WRITE_LOCK:
        path = _today_events_file()
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return entry


def load_events(*, limit: int = 200, trace_id: str | None = None) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    events_dir = _trace_root() / "events"
    if not events_dir.exists():
        return []

    collected: list[dict[str, Any]] = []
    for path in sorted(events_dir.glob("*.jsonl"), reverse=True):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if trace_id and item.get("trace_id") != trace_id:
                continue
            collected.append(item)
            if len(collected) >= limit:
                break
        if len(collected) >= limit:
            break

    collected.reverse()
    return collected


def load_trace(trace_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    return load_events(limit=limit, trace_id=trace_id)

