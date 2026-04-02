import importlib.metadata

from typer.testing import CliRunner

from nouse.cli.main import app

runner = CliRunner()


def test_version_exits_zero_and_prints_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    expected_version = importlib.metadata.version("b76")
    assert f"b76 version {expected_version}" in result.output


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "trace-probe" in result.output
    assert "mission" in result.output
    assert "hitl" in result.output
    assert "knowledge-audit" in result.output
    assert "memory-audit" in result.output
    assert "consolidation-run" in result.output


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "B76 Front Door" in result.output
    assert "b76 start me" in result.output


def test_hitl_status_runs():
    result = runner.invoke(app, ["hitl", "status", "--status", "all", "--limit", "1"])
    assert result.exit_code == 0
    assert "HITL" in result.output
