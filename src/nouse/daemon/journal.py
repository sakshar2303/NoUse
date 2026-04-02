"""
b76.daemon.journal — Daglig journal för självutveckling
=======================================================
Skriver en löpande daglig brief så vi kan följa hur systemet resonerar
och utvecklas över tid.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


JOURNAL_DIR = Path.home() / ".local" / "share" / "nouse" / "journal"
DEDUP_STATE_FILE = JOURNAL_DIR / ".trace_dedup_state.json"


def _journal_dedup_window_sec() -> float:
    try:
        return max(0.0, float(os.getenv("NOUSE_JOURNAL_DEDUP_WINDOW_SEC", "45")))
    except Exception:
        return 45.0


def _today_file(now: datetime | None = None) -> Path:
    dt = now or datetime.now(timezone.utc)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    return JOURNAL_DIR / f"{dt.strftime('%Y-%m-%d')}.md"


def _today_research_file(now: datetime | None = None) -> Path:
    dt = now or datetime.now(timezone.utc)
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    return JOURNAL_DIR / f"{dt.strftime('%Y-%m-%d')}.events.jsonl"


def _load_dedup_state() -> dict[str, float]:
    if not DEDUP_STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(DEDUP_STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            out: dict[str, float] = {}
            for k, v in payload.items():
                try:
                    out[str(k)] = float(v)
                except Exception:
                    continue
            return out
    except Exception:
        return {}
    return {}


def _save_dedup_state(state: dict[str, float]) -> None:
    try:
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        DEDUP_STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        pass


def _write_research_event(now: datetime, event: dict[str, Any]) -> None:
    path = _today_research_file(now)
    row = dict(event)
    row.setdefault("ts", now.isoformat())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def write_daily_brief(
    *,
    cycle: int,
    stats: dict[str, Any],
    limbic: Any,
    new_relations: int,
    discoveries: int,
    bisoc_candidates: int,
    queue_stats: dict[str, Any] | None = None,
    queue_tasks: list[dict[str, Any]] | None = None,
    living_state: dict[str, Any] | None = None,
) -> Path:
    """
    Append:a en kort daily brief till dagens journalfil.
    """
    now = datetime.now(timezone.utc)
    path = _today_file(now)

    queue_stats = queue_stats or {}
    queue_tasks = queue_tasks or []
    open_questions = _build_open_questions(queue_tasks)
    living_state = living_state or {}
    homeostasis = living_state.get("homeostasis") if isinstance(living_state, dict) else {}
    drives = living_state.get("drives") if isinstance(living_state, dict) else {}
    reflection = living_state.get("last_reflection") if isinstance(living_state, dict) else {}
    drive_scores = drives.get("scores") if isinstance(drives, dict) else {}

    line = (
        f"- {now.strftime('%H:%M:%S')} UTC · "
        f"cycle={cycle} · "
        f"+rel={new_relations} · discoveries={discoveries} · bisoc={bisoc_candidates} · "
        f"graph={stats.get('concepts','?')}/{stats.get('relations','?')} · "
        f"λ={getattr(limbic, 'lam', 0.0):.3f} · arousal={getattr(limbic, 'arousal', 0.0):.3f}"
    )

    if not path.exists():
        header = (
            f"# b76 Daily Journal — {now.strftime('%Y-%m-%d')} (UTC)\n\n"
            "## Purpose\n"
            "Följa hur modellen utvecklas, vad den gjort, och vilka frågor den själv lyfter.\n\n"
            "## Timeline\n"
        )
        path.write_text(header, encoding="utf-8")

    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        if queue_stats:
            f.write(
                f"  Queue: pending={queue_stats.get('pending',0)} "
                f"in_progress={queue_stats.get('in_progress',0)} "
                f"awaiting_approval={queue_stats.get('awaiting_approval',0)} "
                f"done={queue_stats.get('done',0)} failed={queue_stats.get('failed',0)}\n"
            )
        if isinstance(homeostasis, dict) and homeostasis:
            f.write(
                "  Homeostasis: "
                f"mode={homeostasis.get('mode','steady')} "
                f"energy={_as_float(homeostasis.get('energy'), 0.0):.3f} "
                f"focus={_as_float(homeostasis.get('focus'), 0.0):.3f} "
                f"risk={_as_float(homeostasis.get('risk'), 0.0):.3f}\n"
            )
        if isinstance(drives, dict) and drives:
            f.write(
                "  Drives: "
                f"active={drives.get('active','maintenance')} "
                f"curiosity={_as_float(drive_scores.get('curiosity'), 0.0):.3f} "
                f"maintenance={_as_float(drive_scores.get('maintenance'), 0.0):.3f} "
                f"improvement={_as_float(drive_scores.get('improvement'), 0.0):.3f} "
                f"recovery={_as_float(drive_scores.get('recovery'), 0.0):.3f}\n"
            )
            goals = [str(x).strip() for x in (drives.get("goals") or []) if str(x).strip()]
            if goals:
                f.write("  Internal goals:\n")
                for goal in goals[:3]:
                    f.write(f"  - {goal}\n")
        if isinstance(reflection, dict) and reflection:
            thought = str(reflection.get("thought") or "").strip()
            feeling = str(reflection.get("feeling") or "").strip()
            responsibility = str(reflection.get("responsibility") or "").strip()
            if thought:
                f.write(f"  Thought: {thought}\n")
            if feeling:
                f.write(f"  Feeling: {feeling}\n")
            if responsibility:
                f.write(f"  Responsibility: {responsibility}\n")
        if open_questions:
            f.write("  Open questions:\n")
            for q in open_questions:
                f.write(f"  - {q}\n")
        f.write("\n")

    _write_research_event(
        now,
        {
            "event": "daily_brief",
            "cycle": int(cycle),
            "graph": {
                "concepts": int(stats.get("concepts", 0) or 0),
                "relations": int(stats.get("relations", 0) or 0),
            },
            "limbic": {
                "lam": float(getattr(limbic, "lam", 0.0) or 0.0),
                "arousal": float(getattr(limbic, "arousal", 0.0) or 0.0),
            },
            "delta": {
                "new_relations": int(new_relations),
                "discoveries": int(discoveries),
                "bisoc_candidates": int(bisoc_candidates),
            },
            "queue": queue_stats,
            "open_questions": open_questions,
        },
    )
    return path


def write_cycle_trace(
    *,
    cycle: int,
    stage: str,
    thought: str = "",
    action: str = "",
    result: str = "",
    details: dict[str, Any] | None = None,
) -> Path:
    """
    Append:a en strukturerad operativ trace-post till dagens journal.

    Varje post fångar:
    - stage: vilket steg i loopen som kördes
    - thought: kort operativ tanke (sammanfattad, ej rå intern tokenkedja)
    - action: vad systemet gjorde
    - result: utfall i klartext
    - details: strukturerad metadata
    """
    now = datetime.now(timezone.utc)
    path = _today_file(now)

    if not path.exists():
        header = (
            f"# b76 Daily Journal — {now.strftime('%Y-%m-%d')} (UTC)\n\n"
            "## Purpose\n"
            "Följa hur modellen utvecklas, vad den gjort, och vilka frågor den själv lyfter.\n\n"
            "## Timeline\n"
        )
        path.write_text(header, encoding="utf-8")

    clean_stage = str(stage or "").strip() or "unknown_stage"
    clean_thought = str(thought or "").strip()
    clean_action = str(action or "").strip()
    clean_result = str(result or "").strip()
    payload = details or {}

    dedup_payload = {
        "cycle": int(cycle),
        "stage": clean_stage,
        "thought": clean_thought,
        "action": clean_action,
        "result": clean_result,
        "details": payload,
    }
    dedup_key = hashlib.sha1(
        json.dumps(dedup_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    now_ts = now.timestamp()
    dedup_window = _journal_dedup_window_sec()
    if dedup_window > 0:
        state = _load_dedup_state()
        last_ts = float(state.get(dedup_key, 0.0) or 0.0)
        if now_ts - last_ts < dedup_window:
            return path
        state[dedup_key] = now_ts
        # Håll state liten och relevant.
        if len(state) > 3000:
            cutoff = now_ts - max(dedup_window * 4.0, 600.0)
            state = {k: v for k, v in state.items() if v >= cutoff}
        _save_dedup_state(state)

    with path.open("a", encoding="utf-8") as f:
        f.write(
            f"- {now.strftime('%H:%M:%S')} UTC · cycle={cycle} · stage={clean_stage}\n"
        )
        if clean_thought:
            f.write(f"  Thought: {clean_thought}\n")
        if clean_action:
            f.write(f"  Action: {clean_action}\n")
        if clean_result:
            f.write(f"  Result: {clean_result}\n")
        if payload:
            f.write(
                "  Details: "
                + json.dumps(payload, ensure_ascii=False, sort_keys=True)
                + "\n"
            )
        f.write("\n")

    _write_research_event(
        now,
        {
            "event": "cycle_trace",
            "cycle": int(cycle),
            "stage": clean_stage,
            "thought": clean_thought,
            "action": clean_action,
            "result": clean_result,
            "details": payload,
        },
    )
    return path


def latest_journal_file() -> Path | None:
    if not JOURNAL_DIR.exists():
        return None
    files = sorted(JOURNAL_DIR.glob("*.md"))
    return files[-1] if files else None


def _build_open_questions(tasks: list[dict[str, Any]]) -> list[str]:
    questions: list[str] = []
    for t in tasks:
        if str(t.get("status", "")) != "pending":
            continue
        domain = str(t.get("domain", "okänd"))
        concepts = [str(c) for c in (t.get("concepts") or [])][:3]
        if concepts:
            questions.append(
                f"Hur kopplas {', '.join(concepts)} i domänen '{domain}' med stark evidens?"
            )
        else:
            questions.append(f"Vilket kunskapsgap är mest kritiskt i domänen '{domain}'?")
        if len(questions) >= 3:
            break
    return questions
