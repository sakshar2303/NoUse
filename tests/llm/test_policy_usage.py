from __future__ import annotations

from pathlib import Path

from nouse.llm.policy import (
    load_policy,
    resolve_model_candidates,
    set_workload_candidates,
)
from nouse.llm.usage import list_usage, record_usage, usage_summary


def test_policy_candidates_override_defaults(tmp_path: Path):
    path = tmp_path / "model_policy.json"
    row = set_workload_candidates(
        workload="extract",
        candidates=["model_a", "model_b"],
        provider="ollama",
        path=path,
    )
    assert row["workload"] == "extract"
    assert row["candidates"] == ["model_a", "model_b"]
    merged = resolve_model_candidates(
        "extract",
        ["default_x", "model_b"],
        path=path,
    )
    assert merged[0] == "model_a"
    assert "default_x" in merged
    policy = load_policy(path)
    assert "extract" in (policy.get("workloads") or {})


def test_policy_qualifies_openai_compatible_candidates(tmp_path: Path):
    path = tmp_path / "model_policy.json"
    set_workload_candidates(
        workload="chat",
        candidates=["minimax-m2.7:cloud", "ollama/qwen3.5:latest"],
        provider="openai_compatible",
        path=path,
    )
    merged = resolve_model_candidates("chat", ["qwen3.5:latest"], path=path)
    assert merged[0] == "openai_compatible/minimax-m2.7:cloud"
    assert "ollama/qwen3.5:latest" in merged
    assert "openai_compatible/qwen3.5:latest" in merged


def test_default_policy_includes_agent_workload(tmp_path: Path):
    path = tmp_path / "model_policy.json"
    policy = load_policy(path)
    workloads = policy.get("workloads") or {}
    assert "agent" in workloads


def test_usage_summary_aggregates_rows(tmp_path: Path):
    path = tmp_path / "usage.jsonl"
    record_usage(
        {
            "session_id": "s1",
            "workload": "chat",
            "provider": "ollama",
            "model": "m1",
            "status": "succeeded",
            "latency_ms": 120,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "cost_usd": 0.0,
        },
        path=path,
    )
    record_usage(
        {
            "session_id": "s1",
            "workload": "chat",
            "provider": "ollama",
            "model": "m1",
            "status": "failed",
            "latency_ms": 220,
            "prompt_tokens": 5,
            "completion_tokens": 0,
            "total_tokens": 5,
            "cost_usd": 0.0,
        },
        path=path,
    )
    rows = list_usage(limit=10, path=path)
    assert len(rows) == 2
    summary = usage_summary(limit=50, path=path)
    assert summary["rows"] == 2
    assert summary["failed"] == 1
    assert summary["total_tokens"] == 35
    assert summary["by_model"][0]["model"] == "m1"
