from __future__ import annotations

from pathlib import Path

from nouse.mcp_gateway import gateway


def test_kernel_write_and_retrieve_memory(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOUSE_MEMORY_DIR", str(tmp_path / "memory"))

    write = gateway.kernel_write_episode(
        "Fungi and quantum tunneling can be bridge hypotheses.",
        source="test",
        domain_hint="research",
    )
    assert write["status"] == "ok"

    ctx = gateway.kernel_get_working_context(limit=5)
    assert ctx["results"]
    assert any("fungi" in (row.get("summary") or "").lower() for row in ctx["results"])

    found = gateway.kernel_retrieve_memory("fungi", limit=5)
    assert found["results"]
    assert any(row["source"] == "working" for row in found["results"])


def test_kernel_guarded_ops_blocked_without_policy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOUSE_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.delenv("NOUSE_KERNEL_ALLOW_GUARDED_WRITES", raising=False)
    monkeypatch.delenv("NOUSE_KERNEL_APPROVAL_TOKEN", raising=False)

    blocked = gateway.kernel_promote_memory(max_episodes=3, strict_min_evidence=0.7)
    assert blocked.get("error") == "guarded_write_blocked"

    blocked2 = gateway.kernel_execute_self_update("apply patch")
    assert blocked2.get("error") == "guarded_write_blocked"


def test_kernel_guarded_ops_allow_with_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOUSE_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("NOUSE_KERNEL_ALLOW_GUARDED_WRITES", "1")

    out = gateway.kernel_promote_memory(max_episodes=2, strict_min_evidence=0.65)
    assert out.get("status") == "accepted"
    assert out.get("operation") == "kernel_promote_memory"


def test_kernel_link_and_fact_proposal(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOUSE_MEMORY_DIR", str(tmp_path / "memory"))

    fact = gateway.kernel_propose_fact(
        "Residual-edge cognition requires inspectable persistence.",
        evidence_ref="paper://brain-database-thesis",
        confidence=0.82,
    )
    assert fact["status"] == "accepted_as_proposal"

    link = gateway.kernel_link_concepts(
        "fungi",
        "bridge_to",
        "quantum_tunneling",
        why="Cross-domain bisociation candidate",
        evidence_score=0.73,
    )
    assert link["status"] == "ok"

    ctx = gateway.kernel_get_working_context(limit=10)
    summaries = "\n".join((row.get("summary") or "") for row in ctx["results"])
    assert "bridge_to" in summaries
