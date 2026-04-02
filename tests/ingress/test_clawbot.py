from __future__ import annotations

from pathlib import Path

from nouse.daemon.system_events import (
    peek_system_event_entries,
    peek_wake_reasons,
    reset_system_event_state_for_test,
)
from nouse.ingress.clawbot import (
    approve_clawbot_pairing,
    get_clawbot_allowlist,
    ingest_clawbot_event,
)


def test_clawbot_pairing_then_ingest(monkeypatch, tmp_path: Path):
    allowlist_path = tmp_path / "allowlist.json"
    captured_session: dict = {}

    def _fake_ensure_session(session_id: str, **kwargs):  # noqa: ANN001
        captured_session["id"] = session_id
        captured_session["meta"] = dict(kwargs.get("meta") or {})
        return {"id": session_id}

    from nouse.ingress import clawbot as cb

    monkeypatch.setattr(cb, "ensure_session", _fake_ensure_session)
    reset_system_event_state_for_test()
    try:
        first = ingest_clawbot_event(
            text="analyze this",
            channel="ops",
            actor_id="u123",
            strict_pairing=True,
            allowlist_path=allowlist_path,
        )
        assert first["accepted"] is False
        assert first["requires_pairing"] is True
        code = str(first["pairing_code"])

        approved = approve_clawbot_pairing("ops", code, path=allowlist_path)
        assert approved is not None
        assert approved["actor_id"] == "u123"

        second = ingest_clawbot_event(
            text="analyze this",
            channel="ops",
            actor_id="u123",
            strict_pairing=True,
            mode="next-heartbeat",
            allowlist_path=allowlist_path,
        )
        assert second["accepted"] is True
        assert second["queued"] is True
        assert second["wake_requested"] is False
        assert second["session_id"].startswith("clawbot_")
        assert captured_session["meta"]["ingress"] == "clawbot"

        events = peek_system_event_entries(limit=10, session_id=second["session_id"])
        assert len(events) == 1
        assert events[0]["text"] == "analyze this"
        assert peek_wake_reasons(limit=10) == []
    finally:
        reset_system_event_state_for_test()


def test_clawbot_allowlist_snapshot(tmp_path: Path):
    allowlist_path = tmp_path / "allowlist.json"
    row = ingest_clawbot_event(
        text="hello",
        channel="research",
        actor_id="actor42",
        strict_pairing=True,
        allowlist_path=allowlist_path,
    )
    assert row["requires_pairing"] is True
    snap = get_clawbot_allowlist("research", path=allowlist_path)
    assert snap["channel"] == "research"
    assert snap["allowed"] == []
    assert len(snap["pending"]) == 1
