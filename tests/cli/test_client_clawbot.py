from __future__ import annotations

import nouse.client as client


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = dict(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return dict(self._payload)


def test_brain_clawbot_ingest_posts_expected_payload(monkeypatch):
    called: dict = {}

    def _fake_post(url, json, timeout):  # noqa: A002
        called["url"] = url
        called["json"] = dict(json)
        called["timeout"] = timeout
        return _FakeResponse({"ok": True, "accepted": True})

    monkeypatch.setattr(client.httpx, "post", _fake_post)
    row = client.brain_clawbot_ingest(
        text="hej",
        channel="ops",
        actor_id="u1",
        mode="now",
        strict_pairing=True,
        timeout=9.0,
    )

    assert called["url"].endswith("/api/ingress/clawbot")
    assert called["json"]["channel"] == "ops"
    assert called["json"]["actor_id"] == "u1"
    assert row["accepted"] is True


def test_brain_clawbot_allowlist_calls_expected_endpoint(monkeypatch):
    called: dict = {}

    def _fake_get(url, params=None, timeout=None):  # noqa: ANN001
        called["url"] = url
        called["params"] = dict(params or {})
        called["timeout"] = timeout
        return _FakeResponse({"ok": True, "allowed": [], "pending": []})

    monkeypatch.setattr(client.httpx, "get", _fake_get)
    row = client.brain_clawbot_allowlist(channel="research", timeout=7.0)

    assert called["url"].endswith("/api/ingress/clawbot/allowlist")
    assert called["params"]["channel"] == "research"
    assert row["ok"] is True


def test_brain_clawbot_approve_posts_expected_endpoint(monkeypatch):
    called: dict = {}

    def _fake_post(url, json, timeout):  # noqa: A002
        called["url"] = url
        called["json"] = dict(json)
        called["timeout"] = timeout
        return _FakeResponse({"ok": True, "actor_id": "u1"})

    monkeypatch.setattr(client.httpx, "post", _fake_post)
    row = client.brain_clawbot_approve(channel="ops", code="ABC123", timeout=6.0)

    assert called["url"].endswith("/api/ingress/clawbot/approve")
    assert called["json"]["channel"] == "ops"
    assert called["json"]["code"] == "ABC123"
    assert row["ok"] is True
