from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import nouse.daemon.journal as journal


def test_write_daily_brief_includes_living_reflection(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path)
    limbic = SimpleNamespace(lam=0.62, arousal=0.57)
    path = journal.write_daily_brief(
        cycle=7,
        stats={"concepts": 40, "relations": 90},
        limbic=limbic,
        new_relations=3,
        discoveries=1,
        bisoc_candidates=2,
        queue_stats={"pending": 1, "in_progress": 0, "awaiting_approval": 0, "done": 4, "failed": 0},
        queue_tasks=[],
        living_state={
            "homeostasis": {"mode": "focus", "energy": 0.72, "focus": 0.81, "risk": 0.31},
            "drives": {
                "active": "improvement",
                "scores": {"curiosity": 0.4, "maintenance": 0.3, "improvement": 0.8, "recovery": 0.2},
                "goals": ["tighten evidence quality", "reduce uncertainty in key domains"],
            },
            "last_reflection": {
                "thought": "Mode=focus, active_drive=improvement.",
                "feeling": "focused and disciplined",
                "responsibility": "keep boundaries and evidentiary discipline",
            },
        },
    )
    text = path.read_text(encoding="utf-8")
    assert "Homeostasis:" in text
    assert "Drives:" in text
    assert "Thought:" in text
    assert "Feeling:" in text
    assert "Responsibility:" in text


def test_write_cycle_trace_records_stage_thought_action_result(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(journal, "JOURNAL_DIR", tmp_path)
    path = journal.write_cycle_trace(
        cycle=11,
        stage="source_ingest",
        thought="Prioriterar evidens före volym.",
        action="Skannar källor och extraherar relationer.",
        result="Docs=5, +rels=9, errors=0.",
        details={"docs_processed": 5, "added_relations": 9, "errors": 0},
    )
    text = path.read_text(encoding="utf-8")
    assert "stage=source_ingest" in text
    assert "Thought: Prioriterar evidens före volym." in text
    assert "Action: Skannar källor och extraherar relationer." in text
    assert "Result: Docs=5, +rels=9, errors=0." in text
    assert '"docs_processed": 5' in text
