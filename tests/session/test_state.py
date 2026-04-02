from __future__ import annotations

import time
from pathlib import Path

from nouse.session.state import (
    clear_stale_running,
    ensure_session,
    finish_run,
    get_session,
    list_runs,
    session_stats,
    start_run,
)


def test_session_run_lifecycle(tmp_path: Path):
    path = tmp_path / "session_state.json"
    session = ensure_session("alpha", lane="chat", source="test", path=path)
    assert session["id"] == "alpha"
    run = start_run(
        "alpha",
        workload="chat",
        model="m1",
        provider="ollama",
        request_chars=42,
        path=path,
    )
    assert run["session_id"] == "alpha"
    done = finish_run(
        run["run_id"],
        status="succeeded",
        response_chars=128,
        metrics={"x": 1},
        path=path,
    )
    assert done is not None
    session2 = get_session("alpha", path=path)
    assert session2 is not None
    assert session2["status"] == "idle"
    stats = session_stats(path=path)
    assert stats["sessions_total"] == 1
    assert stats["runs_total"] == 1
    rows = list_runs(session_id="alpha", limit=10, path=path)
    assert len(rows) == 1
    assert rows[0]["status"] == "succeeded"


def test_clear_stale_running_marks_idle(tmp_path: Path):
    path = tmp_path / "session_state.json"
    run = start_run(
        "beta",
        workload="agent",
        model="m2",
        provider="ollama",
        path=path,
    )
    time.sleep(0.2)
    fixed = clear_stale_running(max_age_sec=0.1, path=path)
    assert isinstance(fixed, list)
    session = get_session("beta", path=path)
    assert session is not None
    assert "beta" in fixed
    assert session["status"] == "idle"
    assert session.get("active_run_id") is None
    # Ensure run can still be finalized after stale check.
    finish_run(run["run_id"], status="cancelled", error="manual", path=path)
