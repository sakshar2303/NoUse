from __future__ import annotations

import argparse
import json
import signal
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, RLock
from typing import Any

from .brain import Brain, FieldEvent


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class BrainRuntime:
    """Long-running runtime wrapper around the canonical Brain kernel."""

    def __init__(
        self,
        state_path: str | Path,
        *,
        autosave_every_cycles: int = 30,
        telemetry_path: str | Path | None = None,
        seed: int = 76031,
    ) -> None:
        self.state_path = Path(state_path).expanduser()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.autosave_every_cycles = max(1, autosave_every_cycles)
        self._lock = RLock()
        self._stop = Event()
        self.brain = self._load_or_init(seed=seed)
        self._last_save_cycle = self.brain.cycle

        # Metrics
        self._metrics_path = self.state_path.parent / "metrics"
        self._metrics_path.mkdir(parents=True, exist_ok=True)
        self._recent_metrics: deque[dict] = deque(maxlen=10_000)
        self._telemetry_path = (
            Path(telemetry_path).expanduser()
            if telemetry_path is not None
            else self.state_path.parent / "brain_live.jsonl"
        )
        self._telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        self._recent_live: deque[dict] = deque(maxlen=10_000)

    def _load_or_init(self, *, seed: int) -> Brain:
        if self.state_path.exists():
            return Brain.load(self.state_path)
        brain = Brain(seed=seed)
        brain.save(self.state_path)
        return brain

    def stop(self) -> None:
        self._stop.set()

    def save(self) -> Path:
        with self._lock:
            out = self.brain.save(self.state_path)
            self._last_save_cycle = self.brain.cycle
            return out

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            crystallized = sum(1 for edge in self.brain.edges.values() if edge.crystallized)
            return {
                "format_version": self.brain.format_version,
                "schema_version": self.brain.schema_version,
                "cycle": self.brain.cycle,
                "nodes": len(self.brain.nodes),
                "edges": len(self.brain.edges),
                "crystallized_edges": crystallized,
                "state_path": str(self.state_path),
            }

    @property
    def telemetry_path(self) -> Path:
        return self._telemetry_path

    def get_gap_map(self) -> dict[str, Any]:
        with self._lock:
            return self.brain.gap_map()

    def get_metrics_snapshot(self, last_n: int = 100) -> dict[str, Any]:
        recent = list(self._recent_metrics)[-last_n:]
        return {
            "total_recorded": len(self._recent_metrics),
            "last_cycles": recent,
        }

    def get_live_view(self, limit_nodes: int = 12, limit_edges: int = 16) -> dict[str, Any]:
        with self._lock:
            return self.brain.live_view(limit_nodes=limit_nodes, limit_edges=limit_edges)

    def get_live_snapshot(self, last_n: int = 120) -> dict[str, Any]:
        recent = list(self._recent_live)[-last_n:]
        if not recent and self._telemetry_path.exists():
            lines = self._telemetry_path.read_text(encoding="utf-8").splitlines()
            recent = []
            for line in lines[-max(1, last_n) :]:
                try:
                    recent.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            total = len(lines)
        else:
            total = len(self._recent_live)
        latest = recent[-1] if recent else None
        return {
            "telemetry_path": str(self._telemetry_path),
            "total_recorded": total,
            "latest": latest,
            "frames": recent,
        }

    def _collect_cycle_metrics(self) -> dict[str, Any]:
        """Collect scalar metrics from current brain state. Call inside _lock."""
        edges = list(self.brain.edges.values())
        n_edges = len(edges)
        crystallized = sum(1 for e in edges if e.crystallized)
        mean_signal = (
            sum(max(0.0, e.path_signal) for e in edges) / n_edges if n_edges else 0.0
        )
        mean_u = sum(e.u for e in edges) / n_edges if n_edges else 0.0
        gm = self.brain.gap_map()
        return {
            "cycle": self.brain.cycle,
            "ts": _now_iso(),
            "crystallized_edges": crystallized,
            "mean_path_signal": round(mean_signal, 4),
            "mean_u": round(mean_u, 4),
            "gap_weak_nodes": len(gm["weak_nodes"]),
            "gap_weak_edges": len(gm["weak_edges"]),
            "total_edges": n_edges,
            "total_nodes": len(self.brain.nodes),
        }

    def _write_metrics(self, m: dict[str, Any]) -> None:
        """Append one cycle metrics record to today's JSONL file."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        daily_file = self._metrics_path / f"{today}.jsonl"
        with daily_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(m) + "\n")

    def _write_live(self, frame: dict[str, Any]) -> None:
        with self._telemetry_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(frame) + "\n")

    def _coerce_events(self, events: list[dict[str, Any]] | None) -> list[FieldEvent]:
        coerced: list[FieldEvent] = []
        for event in events or []:
            coerced.append(
                FieldEvent(
                    edge_id=str(event["edge_id"]),
                    src=str(event["src"]),
                    rel_type=str(event["rel_type"]),
                    tgt=str(event["tgt"]),
                    w_delta=float(event.get("w_delta", 0.0)),
                    r_delta=float(event.get("r_delta", 0.0)),
                    u_delta=float(event.get("u_delta", 0.0)),
                    evidence_score=(
                        None
                        if event.get("evidence_score") is None
                        else float(event["evidence_score"])
                    ),
                    provenance=(
                        None
                        if event.get("provenance") is None
                        else str(event["provenance"])
                    ),
                )
            )
        return coerced

    def step(self, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        with self._lock:
            before = self.brain.cycle
            self.brain.step(self._coerce_events(events))
            crystallized = self.brain.crystallize()
            did_autosave = False
            if self.brain.cycle - self._last_save_cycle >= self.autosave_every_cycles:
                self.brain.save(self.state_path)
                self._last_save_cycle = self.brain.cycle
                did_autosave = True
            metrics = self._collect_cycle_metrics()
            live = self.brain.live_view(limit_nodes=12, limit_edges=16)
            live["ts"] = _now_iso()
            live["crystallized"] = [edge.edge_id for edge in crystallized]

        # File I/O outside lock.
        self._recent_metrics.append(metrics)
        self._write_metrics(metrics)
        self._recent_live.append(live)
        self._write_live(live)

        return {
            "cycle_before": before,
            "cycle_after": metrics["cycle"],
            "crystallized": [edge.edge_id for edge in crystallized],
            "autosaved": did_autosave,
            "live": live,
        }

    def run_forever(self, *, tick_seconds: float = 1.0) -> None:
        tick = max(0.05, tick_seconds)
        while not self._stop.is_set():
            self.step()
            time.sleep(tick)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Brain Kernel runtime loop (no HTTP).")
    parser.add_argument(
        "--state-path",
        type=Path,
        default=Path("~/.local/share/brain-db-core/brain_image.json").expanduser(),
    )
    parser.add_argument("--tick-seconds", type=float, default=1.0)
    parser.add_argument("--autosave-every-cycles", type=int, default=30)
    parser.add_argument(
        "--telemetry-path",
        type=Path,
        default=Path("~/.local/share/brain-db-core/brain_live.jsonl").expanduser(),
    )
    parser.add_argument("--seed", type=int, default=76031)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    runtime = BrainRuntime(
        args.state_path,
        autosave_every_cycles=args.autosave_every_cycles,
        telemetry_path=args.telemetry_path,
        seed=args.seed,
    )

    def _signal_handler(signum: int, _frame: Any) -> None:
        runtime.stop()
        print(json.dumps({"signal": signum, "action": "shutdown_requested"}))

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    print(
        json.dumps(
            {
                "event": "brain_runtime_started",
                "state_path": str(runtime.state_path),
                "telemetry_path": str(runtime.telemetry_path),
                "tick_seconds": args.tick_seconds,
                "autosave_every_cycles": runtime.autosave_every_cycles,
            }
        )
    )

    try:
        runtime.run_forever(tick_seconds=args.tick_seconds)
    finally:
        out = runtime.save()
        print(json.dumps({"event": "brain_runtime_saved", "path": str(out)}))


if __name__ == "__main__":
    main()
