from __future__ import annotations

from nouse.trace.output_trace import (
    build_attack_plan,
    load_events,
    new_trace_id,
    record_event,
)


def test_record_and_filter_trace_events(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUSE_TRACE_DIR", str(tmp_path))
    tid_a = new_trace_id("a")
    tid_b = new_trace_id("b")

    record_event(tid_a, "chat.request", endpoint="/api/chat", payload={"query": "hej"})
    record_event(tid_b, "chat.request", endpoint="/api/chat", payload={"query": "annan"})
    record_event(tid_a, "chat.response", endpoint="/api/chat", payload={"response": "ok"})

    all_events = load_events(limit=10)
    assert len(all_events) == 3
    only_a = load_events(limit=10, trace_id=tid_a)
    assert len(only_a) == 2
    assert [e["event"] for e in only_a] == ["chat.request", "chat.response"]


def test_attack_plan_classifies_question_claim_and_assumption():
    plan = build_attack_plan(
        "Kan systemet lära sig över tid? Om modellen antar fel premiss blir svaret skevt. "
        "LLM-lagret är semantiskt."
    )
    assert plan["questions"]
    assert plan["assumptions"]
    assert plan["claims"]
    assert "collect_graph_context" in plan["steps"]

