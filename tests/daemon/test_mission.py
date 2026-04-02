from __future__ import annotations

from pathlib import Path

from nouse.daemon.mission import (
    append_cycle_metric,
    build_seed_tasks,
    load_mission,
    read_recent_metrics,
    save_mission,
)


class _FakeField:
    def __init__(self) -> None:
        self._domains = ["artificiell intelligens", "neurovetenskap"]
        self._concepts = {
            "artificiell intelligens": [
                {"name": "agent loop"},
                {"name": "model failover"},
                {"name": "observability"},
            ],
            "neurovetenskap": [
                {"name": "hippocampus"},
                {"name": "amygdala"},
            ],
        }

    def domains(self) -> list[str]:
        return list(self._domains)

    def concepts(self, domain: str) -> list[dict]:
        return list(self._concepts.get(domain, []))


def test_save_and_load_mission_roundtrip(tmp_path: Path):
    mpath = tmp_path / "mission.json"
    saved = save_mission(
        "Bygg en autonom, spårbar hjärna.",
        north_star="Ny standard för AI-modellering",
        focus_domains=["artificiell intelligens", "neurovetenskap", "artificiell intelligens"],
        kpis=["coverage_complete >= 0.8"],
        constraints=["inga dolda beslut"],
        path=mpath,
    )
    loaded = load_mission(mpath)
    assert loaded is not None
    assert loaded["mission"] == "Bygg en autonom, spårbar hjärna."
    assert loaded["north_star"] == "Ny standard för AI-modellering"
    assert loaded["focus_domains"] == ["artificiell intelligens", "neurovetenskap"]
    assert loaded["kpis"] == ["coverage_complete >= 0.8"]
    assert loaded["constraints"] == ["inga dolda beslut"]
    assert int(saved["version"]) == 1


def test_build_seed_tasks_from_mission_focus_domains():
    mission = {
        "mission": "Bygg ny standard",
        "north_star": "Hjärnarkitektur med evidens",
        "focus_domains": ["artificiell intelligens", "systemteori", "neurovetenskap"],
    }
    tasks = build_seed_tasks(_FakeField(), mission, max_new=3)
    assert len(tasks) == 3
    gap_types = {t["gap_type"] for t in tasks}
    assert "mission_focus_domain" in gap_types
    assert "mission_bootstrap_domain" in gap_types


def test_append_and_read_recent_metrics(tmp_path: Path):
    metrics_path = tmp_path / "mission_metrics.jsonl"
    mission = {
        "mission": "Bygg ny standard",
        "north_star": "Hjärnarkitektur med evidens",
        "focus_domains": ["artificiell intelligens"],
        "version": 2,
    }
    append_cycle_metric(
        mission=mission,
        cycle=7,
        graph_stats={"concepts": 120, "relations": 340},
        queue={"pending": 2, "in_progress": 1, "done": 5, "failed": 0},
        limbic={"lambda": 0.9, "arousal": 1.0, "dopamine": 0.6, "noradrenaline": 0.5},
        new_relations=11,
        discoveries=3,
        bisoc_candidates=4,
        knowledge_coverage={"context": 0.8, "facts": 0.7, "strong_facts": 0.6, "complete": 0.55},
        path=metrics_path,
    )
    rows = read_recent_metrics(limit=5, path=metrics_path)
    assert len(rows) == 1
    row = rows[0]
    assert int(row["cycle"]) == 7
    assert int(row["graph"]["concepts"]) == 120
    assert float(row["knowledge_coverage"]["complete"]) == 0.55
