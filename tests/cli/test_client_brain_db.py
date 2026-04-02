from __future__ import annotations

import nouse.client as client


class _FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200):
        self._payload = dict(payload)
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return dict(self._payload)


def test_brain_db_running_checks_health_ok(monkeypatch):
    called: dict = {}

    def _fake_get(url, params=None, timeout=None):  # noqa: ANN001
        called["url"] = url
        called["params"] = params
        called["timeout"] = timeout
        return _FakeResponse({"ok": True})

    monkeypatch.setattr(client.httpx, "get", _fake_get)
    assert client.brain_db_running() is True
    assert called["url"].endswith("/health")


def test_brain_get_state_calls_state_endpoint(monkeypatch):
    called: dict = {}

    def _fake_get(url, params=None, timeout=None):  # noqa: ANN001
        called["url"] = url
        called["params"] = params
        called["timeout"] = timeout
        return _FakeResponse({"cycle": 123, "nodes": 3, "edges": 4})

    monkeypatch.setattr(client.httpx, "get", _fake_get)
    row = client.brain_get_state(timeout=9.0)

    assert called["url"].endswith("/state")
    assert row["cycle"] == 123


def test_brain_get_metrics_passes_last_n(monkeypatch):
    called: dict = {}

    def _fake_get(url, params=None, timeout=None):  # noqa: ANN001
        called["url"] = url
        called["params"] = dict(params or {})
        called["timeout"] = timeout
        return _FakeResponse({"total_recorded": 5, "last_cycles": []})

    monkeypatch.setattr(client.httpx, "get", _fake_get)
    row = client.brain_get_metrics(last_n=42, timeout=7.0)

    assert called["url"].endswith("/metrics")
    assert called["params"]["last_n"] == 42
    assert row["total_recorded"] == 5


def test_brain_step_posts_events(monkeypatch):
    called: dict = {}

    def _fake_post(url, json, timeout):  # noqa: A002
        called["url"] = url
        called["json"] = dict(json)
        called["timeout"] = timeout
        return _FakeResponse({"cycle_before": 4, "cycle_after": 5})

    monkeypatch.setattr(client.httpx, "post", _fake_post)
    row = client.brain_step(
        events=[{"edge_id": "e1", "src": "a", "rel_type": "rel", "tgt": "b"}],
        timeout=8.0,
    )

    assert called["url"].endswith("/step")
    assert isinstance(called["json"]["events"], list)
    assert row["cycle_after"] == 5
