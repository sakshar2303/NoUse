from __future__ import annotations

from typer.testing import CliRunner

import nouse.client as client
from nouse.cli.main import app

runner = CliRunner()


def test_brain_status_online(monkeypatch):
    monkeypatch.setattr(client, "brain_db_running", lambda: True)
    monkeypatch.setattr(
        client,
        "brain_get_health",
        lambda timeout=5.0: {  # noqa: ARG005
            "ok": True,
            "runtime": {"cycle": 7, "nodes": 3, "edges": 4, "crystallized_edges": 1},
        },
    )

    result = runner.invoke(app, ["brain", "status"])
    assert result.exit_code == 0
    assert "brain-db-core online" in result.output
    assert "cycle=7" in result.output


def test_brain_step_rejects_invalid_events_json():
    result = runner.invoke(app, ["brain", "step", "--events-json", "{broken"])
    assert result.exit_code == 1
    assert "Ogiltig --events-json" in result.output
