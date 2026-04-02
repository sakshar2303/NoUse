from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from nouse.self_layer.living_core import (
    append_identity_memory,
    ensure_living_core,
    identity_prompt_fragment,
    load_living_core,
    record_self_training_iteration,
    update_living_core,
)


def test_ensure_living_core_creates_default_state(tmp_path: Path):
    path = tmp_path / "living_core.json"
    state = ensure_living_core(path=path)
    assert path.exists()
    assert state["version"] >= 1
    assert "identity" in state
    assert "mission" in state["identity"]
    assert state["identity"]["name"] == "B76"
    assert "self_training" in state
    assert "formula" in (state.get("self_training") or {})


def test_update_living_core_updates_homeostasis_drives_and_reflection(tmp_path: Path):
    path = tmp_path / "living_core.json"
    ensure_living_core(path=path)
    limbic = SimpleNamespace(
        dopamine=0.7,
        arousal=0.58,
        acetylcholine=1.2,
        performance=0.84,
        lam=0.67,
    )
    state = update_living_core(
        cycle=12,
        limbic=limbic,
        graph_stats={"concepts": 120, "relations": 240},
        queue_stats={"pending": 2, "in_progress": 1, "awaiting_approval": 0, "failed": 0},
        session_stats={"sessions_running": 1},
        new_relations=6,
        discoveries=2,
        bisoc_candidates=1,
        path=path,
    )
    homeo = state["homeostasis"]
    drives = state["drives"]
    reflection = state["last_reflection"]
    assert 0.0 <= float(homeo["energy"]) <= 1.0
    assert 0.0 <= float(homeo["focus"]) <= 1.0
    assert 0.0 <= float(homeo["risk"]) <= 1.0
    assert drives["active"] in {"curiosity", "maintenance", "improvement", "recovery"}
    assert reflection["cycle"] == 12
    assert isinstance(reflection["thought"], str) and reflection["thought"]
    memories = (state.get("identity") or {}).get("memories") or []
    assert memories


def test_append_identity_memory_keeps_recent_limit(tmp_path: Path):
    path = tmp_path / "living_core.json"
    ensure_living_core(path=path)
    for idx in range(260):
        append_identity_memory(
            f"note-{idx}",
            tags=["test"],
            session_id="s1",
            run_id=f"run-{idx}",
            kind="unit",
            path=path,
        )
    state = load_living_core(path=path)
    memories = (state.get("identity") or {}).get("memories") or []
    assert len(memories) == 240
    assert memories[-1]["note"] == "note-259"
    assert memories[0]["note"] == "note-20"


def test_identity_prompt_fragment_contains_identity_and_state(tmp_path: Path):
    path = tmp_path / "living_core.json"
    state = ensure_living_core(path=path)
    prompt = identity_prompt_fragment(state)
    assert "Persistent identity profile" in prompt
    assert "mission:" in prompt
    assert "Current regulation" in prompt
    assert "Reflection" in prompt
    assert "Self-training" in prompt


def test_record_self_training_iteration_updates_state_and_memory(tmp_path: Path):
    path = tmp_path / "living_core.json"
    ensure_living_core(path=path)
    state = record_self_training_iteration(
        known_data_sources=["graph", "web", "conversation"],
        meta_reflection="assumptions=none",
        reflection="Kort reflektion om senaste svar.",
        session_id="s1",
        run_id="r1",
        path=path,
    )
    st = state.get("self_training") or {}
    assert int(st.get("iterations", 0)) >= 1
    assert "graph" in (st.get("source_usage") or {})
    last = st.get("last") or {}
    assert "web" in (last.get("known_data_sources") or [])
    assert "assumptions=" in str(last.get("meta_reflection") or "")
    memories = (state.get("identity") or {}).get("memories") or []
    assert any(str(m.get("kind") or "") == "self_training" for m in memories)
