from __future__ import annotations

import json

import httpx

import nouse.client as client


class _FakeResponse:
    def __init__(
        self,
        lines,
        *,
        raise_iter_exc: Exception | None = None,
        raise_after_n_lines: int | None = None,
    ):
        self._lines = list(lines)
        self._raise_iter_exc = raise_iter_exc
        self._raise_after_n_lines = raise_after_n_lines

    def raise_for_status(self) -> None:
        return None

    def iter_lines(self):
        if self._raise_iter_exc is not None:
            raise self._raise_iter_exc
        for idx, line in enumerate(self._lines, start=1):
            yield line
            if self._raise_after_n_lines is not None and idx >= self._raise_after_n_lines:
                raise httpx.RemoteProtocolError("incomplete chunked read")


class _FakeStreamCtx:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, exc_type, exc, tb):
        return False


def test_stream_chat_parses_ndjson(monkeypatch):
    payload = [
        json.dumps({"type": "status", "msg": "x"}),
        "",
        json.dumps({"type": "done", "msg": "klar"}),
    ]

    def _fake_stream(*args, **kwargs):
        return _FakeStreamCtx(_FakeResponse(payload))

    monkeypatch.setattr(client.httpx, "stream", _fake_stream)
    rows = list(client.stream_chat("hej", session_id="s1"))
    assert len(rows) == 2
    assert rows[0]["type"] == "status"
    assert rows[1]["type"] == "done"


def test_stream_chat_converts_remote_protocol_error_to_error_event(monkeypatch):
    monkeypatch.setattr(client, "_CHAT_STREAM_CONNECT_RETRIES", 1)

    def _fake_stream(*args, **kwargs):
        return _FakeStreamCtx(
            _FakeResponse(
                [],
                raise_iter_exc=httpx.RemoteProtocolError("incomplete chunked read"),
            )
        )

    monkeypatch.setattr(client.httpx, "stream", _fake_stream)
    rows = list(client.stream_chat("hej", session_id="s1"))
    assert len(rows) == 1
    assert rows[0]["type"] == "error"
    assert "RemoteProtocolError" in rows[0]["msg"]


def test_stream_chat_retries_remote_protocol_error_before_any_event(monkeypatch):
    monkeypatch.setattr(client, "_CHAT_STREAM_CONNECT_RETRIES", 2)
    monkeypatch.setattr(client, "_CHAT_STREAM_RETRY_BACKOFF_SEC", 0.0)

    calls = {"n": 0}

    def _fake_stream(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeStreamCtx(
                _FakeResponse(
                    [],
                    raise_iter_exc=httpx.RemoteProtocolError("incomplete chunked read"),
                )
            )
        return _FakeStreamCtx(
            _FakeResponse(
                [
                    json.dumps({"type": "status", "msg": "ok"}),
                    json.dumps({"type": "done", "msg": "klart"}),
                ]
            )
        )

    monkeypatch.setattr(client.httpx, "stream", _fake_stream)
    rows = list(client.stream_chat("hej", session_id="s1"))
    assert calls["n"] == 2
    assert rows[0]["type"] == "status"
    assert "Försöker igen" in rows[0]["msg"]
    assert rows[-1]["type"] == "done"


def test_stream_chat_does_not_retry_remote_protocol_error_after_partial_output(monkeypatch):
    monkeypatch.setattr(client, "_CHAT_STREAM_CONNECT_RETRIES", 3)
    monkeypatch.setattr(client, "_CHAT_STREAM_RETRY_BACKOFF_SEC", 0.0)

    calls = {"n": 0}

    def _fake_stream(*args, **kwargs):
        calls["n"] += 1
        return _FakeStreamCtx(
            _FakeResponse(
                [json.dumps({"type": "status", "msg": "börjar"})],
                raise_after_n_lines=1,
            )
        )

    monkeypatch.setattr(client.httpx, "stream", _fake_stream)
    rows = list(client.stream_chat("hej", session_id="s1"))
    assert calls["n"] == 1
    assert rows[0]["type"] == "status"
    assert rows[-1]["type"] == "error"
    assert "RemoteProtocolError" in rows[-1]["msg"]


def test_stream_chat_converts_read_timeout_to_error_event(monkeypatch):
    def _fake_stream(*args, **kwargs):
        return _FakeStreamCtx(
            _FakeResponse(
                [],
                raise_iter_exc=httpx.ReadTimeout("read timed out"),
            )
        )

    monkeypatch.setattr(client.httpx, "stream", _fake_stream)
    rows = list(client.stream_chat("hej", session_id="s1"))
    assert len(rows) == 1
    assert rows[0]["type"] == "error"
    assert "timeout" in rows[0]["msg"].lower()


def test_stream_chat_emits_error_when_stream_ends_without_terminal_event(monkeypatch):
    payload = [
        json.dumps({"type": "status", "msg": "start"}),
        json.dumps({"type": "tool", "name": "list_domains"}),
    ]

    def _fake_stream(*args, **kwargs):
        return _FakeStreamCtx(_FakeResponse(payload))

    monkeypatch.setattr(client.httpx, "stream", _fake_stream)
    rows = list(client.stream_chat("hej", session_id="s1"))
    assert len(rows) == 3
    assert rows[-1]["type"] == "error"
    assert "utan done/error" in rows[-1]["msg"]
