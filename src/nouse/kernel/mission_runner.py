from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .runtime import BrainRuntime


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MissionKPI:
    metric: str
    op: str
    target: float
    label: str = ""
    required: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MissionKPI:
        return cls(
            metric=str(raw["metric"]),
            op=str(raw.get("op", ">=")),
            target=float(raw["target"]),
            label=str(raw.get("label", raw["metric"])),
            required=bool(raw.get("required", True)),
        )


@dataclass
class MissionContract:
    mission_id: str
    title: str
    final_goal: str
    autonomy_level: str = "L3_guided_autonomy"
    max_cycles_per_run: int = 500
    max_runtime_minutes: float = 60.0
    checkpoint_every_cycles: int = 25
    action_events: list[dict[str, Any]] = field(default_factory=list)
    action_repeat_every_cycles: int = 0
    kpis: list[MissionKPI] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MissionContract:
        return cls(
            mission_id=str(raw["mission_id"]),
            title=str(raw.get("title", raw["mission_id"])),
            final_goal=str(raw["final_goal"]),
            autonomy_level=str(raw.get("autonomy_level", "L3_guided_autonomy")),
            max_cycles_per_run=max(1, int(raw.get("max_cycles_per_run", 500))),
            max_runtime_minutes=max(0.1, float(raw.get("max_runtime_minutes", 60.0))),
            checkpoint_every_cycles=max(1, int(raw.get("checkpoint_every_cycles", 25))),
            action_events=list(raw.get("action_events", [])),
            action_repeat_every_cycles=int(raw.get("action_repeat_every_cycles", 0)),
            kpis=[MissionKPI.from_dict(kpi_raw) for kpi_raw in raw.get("kpis", [])],
            notes=[str(x) for x in raw.get("notes", [])],
        )


def load_mission_contract(path: str | Path) -> MissionContract:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return MissionContract.from_dict(raw)


def _collect_metrics(runtime: BrainRuntime) -> dict[str, float]:
    state = runtime.get_state()
    gap_map = runtime.get_gap_map()
    latest_metric = {}
    metric_snapshot = runtime.get_metrics_snapshot(last_n=1)
    if metric_snapshot["last_cycles"]:
        latest_metric = metric_snapshot["last_cycles"][-1]

    total_edges = float(state.get("edges", 0))
    crystallized_edges = float(state.get("crystallized_edges", 0))
    crystallization_ratio = (crystallized_edges / total_edges) if total_edges > 0 else 0.0

    return {
        "cycle": float(state.get("cycle", 0)),
        "total_nodes": float(state.get("nodes", 0)),
        "total_edges": total_edges,
        "crystallized_edges": crystallized_edges,
        "crystallization_ratio": crystallization_ratio,
        "weak_nodes": float(len(gap_map.get("weak_nodes", []))),
        "weak_edges": float(len(gap_map.get("weak_edges", []))),
        "mean_path_signal": float(latest_metric.get("mean_path_signal", 0.0)),
        "mean_u": float(latest_metric.get("mean_u", 1.0)),
    }


def _compare(actual: float, op: str, target: float) -> bool:
    if op == ">=":
        return actual >= target
    if op == "<=":
        return actual <= target
    if op == ">":
        return actual > target
    if op == "<":
        return actual < target
    if op == "==":
        return actual == target
    raise ValueError(f"unsupported KPI operator: {op}")


def evaluate_kpis(
    contract: MissionContract,
    metric_values: dict[str, float],
) -> tuple[list[dict[str, Any]], bool]:
    evaluations: list[dict[str, Any]] = []
    all_required_passed = True
    for kpi in contract.kpis:
        actual = float(metric_values.get(kpi.metric, 0.0))
        passed = _compare(actual, kpi.op, kpi.target)
        if kpi.required and not passed:
            all_required_passed = False
        evaluations.append(
            {
                "label": kpi.label,
                "metric": kpi.metric,
                "required": kpi.required,
                "rule": f"{kpi.metric} {kpi.op} {kpi.target}",
                "actual": round(actual, 6),
                "passed": passed,
            }
        )
    return evaluations, all_required_passed


def _scheduled_events(contract: MissionContract, cycle_index: int) -> list[dict[str, Any]] | None:
    if not contract.action_events:
        return None
    every = contract.action_repeat_every_cycles
    if every <= 0:
        return contract.action_events if cycle_index == 0 else None
    if cycle_index % every == 0:
        return contract.action_events
    return None


def run_mission(runtime: BrainRuntime, contract: MissionContract) -> dict[str, Any]:
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    checkpoints: list[dict[str, Any]] = []
    stop_reason = "max_cycles_reached"
    last_step: dict[str, Any] | None = None

    for cycle_index in range(contract.max_cycles_per_run):
        elapsed_minutes = (time.monotonic() - started_monotonic) / 60.0
        if elapsed_minutes >= contract.max_runtime_minutes:
            stop_reason = "runtime_budget_exceeded"
            break

        events = _scheduled_events(contract, cycle_index)
        last_step = runtime.step(events=events)

        should_checkpoint = (
            (cycle_index + 1) % contract.checkpoint_every_cycles == 0
            or cycle_index == contract.max_cycles_per_run - 1
        )
        if not should_checkpoint:
            continue

        metrics = _collect_metrics(runtime)
        kpi_results, all_required_passed = evaluate_kpis(contract, metrics)
        checkpoints.append(
            {
                "ts": _now_iso(),
                "cycle_index": cycle_index + 1,
                "metrics": metrics,
                "kpis": kpi_results,
            }
        )
        if all_required_passed:
            stop_reason = "mission_success"
            break

    final_metrics = _collect_metrics(runtime)
    final_kpis, final_required_pass = evaluate_kpis(contract, final_metrics)
    ended_at = _now_iso()
    runtime.save()
    return {
        "mission_id": contract.mission_id,
        "title": contract.title,
        "final_goal": contract.final_goal,
        "autonomy_level": contract.autonomy_level,
        "status": "success" if final_required_pass else "incomplete",
        "stop_reason": stop_reason,
        "started_at": started_at,
        "ended_at": ended_at,
        "last_step": last_step or {},
        "final_metrics": final_metrics,
        "final_kpis": final_kpis,
        "checkpoints": checkpoints,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a mission contract against BrainRuntime.")
    parser.add_argument(
        "--mission",
        type=Path,
        required=True,
        help="Path to mission contract JSON.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path("~/.local/share/brain-db-core/brain_image.json").expanduser(),
    )
    parser.add_argument(
        "--telemetry-path",
        type=Path,
        default=Path("~/.local/share/brain-db-core/brain_live.jsonl").expanduser(),
    )
    parser.add_argument("--autosave-every-cycles", type=int, default=30)
    parser.add_argument("--seed", type=int, default=76031)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Optional path to write mission report JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    mission = load_mission_contract(args.mission)
    runtime = BrainRuntime(
        state_path=args.state_path,
        telemetry_path=args.telemetry_path,
        autosave_every_cycles=args.autosave_every_cycles,
        seed=args.seed,
    )
    report = run_mission(runtime, mission)
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
