from __future__ import annotations

import json
from pathlib import Path

from nouse.daemon import research_queue


def test_enqueue_gap_tasks_accepts_seed_tasks(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(research_queue, "detect_knowledge_gaps", lambda field, max_candidates=10: [])

    queue_path = tmp_path / "queue.json"
    seed = [
        {
            "domain": "artificiell intelligens",
            "concepts": ["agent loop", "observability"],
            "query": "Mission: hitta mekanismer med stark evidens.",
            "rationale": "Mission-seed",
            "priority": 0.99,
            "gap_type": "mission_focus_domain",
            "source": "mission_engine_v1",
        }
    ]

    added = research_queue.enqueue_gap_tasks(
        field=object(),  # detect_knowledge_gaps är monkeypatchad
        max_new=3,
        seed_tasks=seed,
        path=queue_path,
    )

    assert len(added) == 1
    assert added[0]["gap_type"] == "mission_focus_domain"

    rows = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["query"] == "Mission: hitta mekanismer med stark evidens."
