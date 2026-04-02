from __future__ import annotations

from pathlib import Path

from nouse.ingress.allowlist import (
    add_allowed_actor,
    approve_pairing,
    is_allowed,
    list_allowed,
    list_pending,
    request_pairing,
)


def test_pairing_flow_roundtrip(tmp_path: Path):
    path = tmp_path / "allowlist.json"
    req = request_pairing("telegram", "u123", path=path)
    assert req["actor_id"] == "u123"
    assert not is_allowed("telegram", "u123", path=path)
    approved = approve_pairing("telegram", req["code"], path=path)
    assert approved is not None
    assert is_allowed("telegram", "u123", path=path)
    assert list_pending("telegram", path=path) == []
    assert "u123" in list_allowed("telegram", path=path)


def test_add_allowed_actor_directly(tmp_path: Path):
    path = tmp_path / "allowlist.json"
    add_allowed_actor("telegram", "u777", path=path)
    assert is_allowed("telegram", "u777", path=path)
