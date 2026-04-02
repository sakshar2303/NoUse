from __future__ import annotations

import nouse.client as client


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = dict(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return dict(self._payload)


def test_post_system_wake_calls_expected_endpoint(monkeypatch):
    called: dict = {}

    def _fake_post(url, json, timeout):  # noqa: A002
        called["url"] = url
        called["json"] = dict(json)
        called["timeout"] = timeout
        return _FakeResponse({"ok": True, "queued": True, "wake_requested": True})

    monkeypatch.setattr(client.httpx, "post", _fake_post)
    row = client.post_system_wake(
        text="signal",
        session_id="s1",
        source="cli",
        mode="now",
        reason="test",
        context_key="ctx",
        timeout=9.0,
    )

    assert called["url"].endswith("/api/system/wake")
    assert called["json"]["text"] == "signal"
    assert called["json"]["session_id"] == "s1"
    assert called["json"]["mode"] == "now"
    assert row["ok"] is True


def test_get_system_events_calls_expected_endpoint(monkeypatch):
    called: dict = {}

    def _fake_get(url, params, timeout):  # noqa: A002
        called["url"] = url
        called["params"] = dict(params)
        called["timeout"] = timeout
        return _FakeResponse({"ok": True, "events": []})

    monkeypatch.setattr(client.httpx, "get", _fake_get)
    row = client.get_system_events(limit=7, session_id="s1", timeout=4.0)

    assert called["url"].endswith("/api/system/events")
    assert called["params"]["limit"] == 7
    assert called["params"]["session_id"] == "s1"
    assert row["ok"] is True
