from __future__ import annotations

import asyncio

from nouse.daemon import system_events as se


def setup_function() -> None:
    se.reset_system_event_state_for_test()


def test_enqueue_and_dedupe_consecutive_text_per_session():
    assert se.enqueue_system_event("hej", session_id="s1", source="test")
    assert not se.enqueue_system_event("hej", session_id="s1", source="test")
    assert se.enqueue_system_event("hej", session_id="s2", source="test")

    stats = se.system_event_stats()
    assert int(stats.get("pending_total", 0) or 0) == 2
    assert int((stats.get("by_session") or {}).get("s1", 0) or 0) == 1
    assert int((stats.get("by_session") or {}).get("s2", 0) or 0) == 1


def test_drain_by_session_keeps_other_sessions():
    se.enqueue_system_event("one", session_id="s1", source="test")
    se.enqueue_system_event("two", session_id="s2", source="test")
    se.enqueue_system_event("three", session_id="s1", source="test")

    rows = se.drain_system_event_entries(limit=10, session_id="s1")
    assert len(rows) == 2
    assert all(str(r.get("session_id") or "") == "s1" for r in rows)

    remaining = se.peek_system_event_entries(limit=10)
    assert len(remaining) == 1
    assert str(remaining[0].get("session_id") or "") == "s2"


def test_request_wake_sets_bound_event_and_stores_reason():
    wake_event = asyncio.Event()
    se.bind_wake_event(wake_event)

    assert not wake_event.is_set()
    se.request_wake(reason="manual_test", session_id="s1", source="test")
    assert wake_event.is_set()

    reasons = se.consume_wake_reasons(limit=10)
    assert len(reasons) == 1
    assert reasons[0]["reason"] == "manual_test"
    assert reasons[0]["session_id"] == "s1"
