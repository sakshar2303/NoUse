from __future__ import annotations

from pathlib import Path

import nouse.llm.model_router as router


def test_router_status_reports_quality_avg(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(router, "_STATE_PATH", tmp_path / "router.json")
    router.record_model_result("extract", "m1", success=True, quality=0.8)
    router.record_model_result("extract", "m1", success=True, quality=0.6)

    status = router.router_status(workload="extract")
    rows = (status.get("workloads") or {}).get("extract") or []
    assert rows
    assert rows[0]["model"] == "m1"
    assert float(rows[0].get("quality_avg", 0.0)) > 0.0


def test_order_models_prefers_higher_quality_when_failures_equal(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(router, "_STATE_PATH", tmp_path / "router.json")

    for _ in range(3):
        router.record_model_result("extract", "m_high", success=True, quality=0.9)
        router.record_model_result("extract", "m_low", success=True, quality=0.2)

    ordered = router.order_models_for_workload("extract", ["m_low", "m_high"])
    assert ordered[0] == "m_high"
