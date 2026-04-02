from __future__ import annotations

from typer.testing import CliRunner

from nouse.cli.main import app
from nouse.trace.output_trace import build_attack_plan, new_trace_id, record_event

runner = CliRunner()


def test_output_trace_cli_shows_attack_plan_counts(monkeypatch, tmp_path):
    monkeypatch.setenv("NOUSE_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr("nouse.client.daemon_running", lambda: False)

    tid = new_trace_id("test")
    record_event(
        tid,
        "chat.request",
        endpoint="/api/chat",
        payload={
            "query": "Varfor ar trace viktigt?",
            "attack_plan": build_attack_plan("Varfor ar trace viktigt?"),
        },
    )

    result = runner.invoke(app, ["output-trace", "--trace-id", tid, "--limit", "10"])
    assert result.exit_code == 0
    assert "chat.request" in result.output
    assert "plan=Q1/C0/A0" in result.output
