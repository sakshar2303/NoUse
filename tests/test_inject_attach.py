from __future__ import annotations

import sys
from types import SimpleNamespace

import nouse.inject as inject


class _DummyLocalBrain:
    def __init__(self, db_path=None, read_only: bool = False):
        self.db_path = db_path
        self.read_only = read_only


def test_attach_prefers_http_when_daemon_is_online(monkeypatch):
    class _DummyClient:
        def __init__(self, timeout: float = 30.0):
            self.timeout = timeout

    def _fake_get(url: str, timeout: float = 1.0):
        return SimpleNamespace(status_code=200)

    fake_httpx = SimpleNamespace(get=_fake_get, Client=_DummyClient)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    brain = inject.attach(prefer_http=True)

    assert isinstance(brain, inject.NouseBrainHTTP)


def test_attach_falls_back_to_local_brain_when_http_unavailable(monkeypatch):
    def _fake_get(url: str, timeout: float = 1.0):
        raise RuntimeError("daemon offline")

    fake_httpx = SimpleNamespace(get=_fake_get, Client=object)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setattr(inject, "NouseBrain", _DummyLocalBrain)

    brain = inject.attach(prefer_http=True, read_only=True)

    assert isinstance(brain, _DummyLocalBrain)
    assert brain.read_only is True


def test_attach_can_force_local_mode(monkeypatch):
    monkeypatch.setattr(inject, "NouseBrain", _DummyLocalBrain)

    brain = inject.attach(prefer_http=False)

    assert isinstance(brain, _DummyLocalBrain)
