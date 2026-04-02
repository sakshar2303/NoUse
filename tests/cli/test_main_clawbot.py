from __future__ import annotations

from typer.testing import CliRunner

import nouse.client as client
from nouse.cli.main import app

runner = CliRunner()


def test_clawbot_status_prints_allowlist(monkeypatch):
    monkeypatch.setattr(client, "daemon_running", lambda: True)
    monkeypatch.setattr(
        client,
        "brain_clawbot_allowlist",
        lambda channel="default", timeout=5.0: {  # noqa: ARG005
            "ok": True,
            "channel": channel,
            "allowed": ["u1"],
            "pending": [],
        },
    )

    result = runner.invoke(app, ["clawbot", "status", "--channel", "ops"])
    assert result.exit_code == 0
    assert "bridge online" in result.output
    assert "u1" in result.output


def test_clawbot_ingest_requires_text(monkeypatch):
    monkeypatch.setattr(client, "daemon_running", lambda: True)
    result = runner.invoke(app, ["clawbot", "ingest", "--channel", "ops"])
    assert result.exit_code == 1
    assert "Ange --text" in result.output
