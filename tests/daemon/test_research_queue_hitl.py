from __future__ import annotations

import json
from pathlib import Path

from nouse.daemon import research_queue


def test_pause_then_approve_task_after_hitl(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(research_queue, "detect_knowledge_gaps", lambda field, max_candidates=10: [])
    queue_path = tmp_path / "queue.json"

    research_queue.enqueue_gap_tasks(
        field=object(),
        max_new=2,
        seed_tasks=[
            {
                "domain": "artificiell intelligens",
                "concepts": ["agent loop"],
                "query": "mission seed",
                "rationale": "x",
                "priority": 0.99,
                "gap_type": "mission_focus_domain",
            }
        ],
        path=queue_path,
    )
    task = research_queue.claim_next_task(path=queue_path)
    assert task is not None
    task_id = int(task["id"])

    paused = research_queue.pause_task_for_hitl(
        task_id,
        interrupt_id=12,
        reason="hitl required",
        path=queue_path,
    )
    assert paused is not None
    assert paused["status"] == "awaiting_approval"

    approved = research_queue.approve_task_after_hitl(task_id, note="ok", path=queue_path)
    assert approved is not None
    assert approved["status"] == "pending"
    assert bool(approved["hitl_approved"]) is True

    stats = research_queue.queue_stats(path=queue_path)
    assert int(stats["awaiting_approval"]) == 0
    assert int(stats["pending"]) == 1


def test_reject_task_after_hitl(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(research_queue, "detect_knowledge_gaps", lambda field, max_candidates=10: [])
    queue_path = tmp_path / "queue.json"

    research_queue.enqueue_gap_tasks(
        field=object(),
        max_new=1,
        seed_tasks=[
            {
                "domain": "datavetenskap",
                "concepts": ["adam"],
                "query": "seed",
                "rationale": "x",
                "priority": 0.95,
                "gap_type": "fragmented_domain",
            }
        ],
        path=queue_path,
    )
    task = research_queue.claim_next_task(path=queue_path)
    assert task is not None
    task_id = int(task["id"])
    research_queue.pause_task_for_hitl(task_id, interrupt_id=3, reason="review", path=queue_path)

    rejected = research_queue.reject_task_after_hitl(task_id, reason="no", path=queue_path)
    assert rejected is not None
    assert rejected["status"] == "failed"
    assert rejected["hitl_status"] == "rejected"

    stats = research_queue.queue_stats(path=queue_path)
    assert int(stats["failed"]) == 1


def test_retry_failed_tasks_requeues_rows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(research_queue, "detect_knowledge_gaps", lambda field, max_candidates=10: [])
    queue_path = tmp_path / "queue.json"

    research_queue.enqueue_gap_tasks(
        field=object(),
        max_new=1,
        seed_tasks=[
            {
                "domain": "maskininlärning",
                "concepts": ["optimizer"],
                "query": "seed",
                "rationale": "x",
                "priority": 0.8,
                "gap_type": "fragmented_domain",
            }
        ],
        path=queue_path,
    )
    task = research_queue.claim_next_task(path=queue_path)
    assert task is not None
    research_queue.fail_task(int(task["id"]), "fail", path=queue_path)
    rows = json.loads(queue_path.read_text(encoding="utf-8"))
    rows[0]["retry_after"] = None
    queue_path.write_text(json.dumps(rows), encoding="utf-8")
    task = research_queue.claim_next_task(path=queue_path)
    assert task is not None
    research_queue.fail_task(int(task["id"]), "fail", path=queue_path)
    rows = json.loads(queue_path.read_text(encoding="utf-8"))
    rows[0]["retry_after"] = None
    queue_path.write_text(json.dumps(rows), encoding="utf-8")
    task = research_queue.claim_next_task(path=queue_path)
    assert task is not None
    research_queue.fail_task(int(task["id"]), "fail", path=queue_path)

    retried = research_queue.retry_failed_tasks(limit=2, reason="retry", path=queue_path)
    assert len(retried) == 1
    assert retried[0]["status"] == "pending"
    assert retried[0]["last_error"] == "retry"

    rows = research_queue.list_tasks(status="pending", path=queue_path)
    assert len(rows) == 1
