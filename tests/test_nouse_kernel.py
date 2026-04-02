"""
Integrationstester för nouse — den plastiska hjärnan som pip-paket.

Testar att Brain Kernel (alias Kernel) fungerar korrekt via nouse-namespacet:
- Instantiering
- Nod- och kantskapande med residual streams (w, r, u)
- step()-dynamik: residual decay + non-local koherens
- path_signal-beräkning: w + 0.45*r - 0.25*u
- Kristallisering av starka, säkra kanter
"""

import math

import pytest

import nouse


def test_kernel_instantiation():
    """Kernel() skapar ett objekt utan fel."""
    k = nouse.Kernel()
    assert k is not None
    assert k.cycle == 0


def test_kernel_exports():
    """Alla kritiska symboler exporteras från nouse-namespacet."""
    assert hasattr(nouse, "Kernel")
    assert hasattr(nouse, "FieldEvent")
    assert hasattr(nouse, "NodeStateSpace")
    assert hasattr(nouse, "ResidualEdge")
    assert hasattr(nouse, "NeuromodulatorState")
    assert hasattr(nouse, "MEMORY_TIERS")
    assert hasattr(nouse, "NEUROMODULATORS")


def test_memory_tiers():
    """Minnesnivåerna följer biologisk progression."""
    assert nouse.MEMORY_TIERS == ("working", "episodic", "semantic", "procedural")


def test_node_creation():
    """add_node() skapar en nod med korrekta fält."""
    k = nouse.Kernel()
    k.add_node(
        "hippocampus",
        node_type="region",
        label="Hippocampus",
        states={"encoder": 0.7, "spatial": 0.3},
        uncertainty=0.5,
        evidence_score=0.0,
        goal_weight=0.0,
        attrs={},
    )
    node = k.nodes["hippocampus"]
    assert node is not None
    assert node.node_id == "hippocampus"
    assert node.node_type == "region"
    assert node.uncertainty == 0.5


def test_edge_creation_and_path_signal():
    """upsert_edge() skapar en kant med korrekt path_signal: w + 0.45*r - 0.25*u."""
    k = nouse.Kernel()
    k.upsert_edge(
        "e1",
        src="hippocampus",
        rel_type="consolidated_into",
        tgt="cortex",
        w=0.3,
        r=0.0,
        u=0.6,
        provenance="test",
    )
    edge = k.edges["e1"]
    assert edge is not None
    expected = 0.3 + 0.45 * 0.0 - 0.25 * 0.6
    assert abs(edge.path_signal - expected) < 1e-9


def test_residual_decay_after_step():
    """step() applicerar residual decay: r := r * r_decay (default 0.89)."""
    k = nouse.Kernel(r_decay=0.89)
    k.upsert_edge("e1", src="a", rel_type="causes", tgt="b", r=1.0, w=0.1, u=0.2)
    r_before = k.edges["e1"].r
    k.step()
    edge = k.edges["e1"]
    # r ska ha minskat (decay * r_before + liten non-local term, men alltid < r_before för r>0)
    assert edge.r < r_before


def test_step_increments_cycle():
    """Varje step() ökar cycle-räknaren med 1."""
    k = nouse.Kernel()
    assert k.cycle == 0
    k.step()
    assert k.cycle == 1
    k.step()
    assert k.cycle == 2


def test_field_event_mutation():
    """FieldEvent applicerat via step() muterar w, r, u korrekt."""
    k = nouse.Kernel()
    k.upsert_edge("e1", src="x", rel_type="regulates", tgt="y", w=0.1, r=0.0, u=0.8)
    event = nouse.FieldEvent(
        edge_id="e1",
        src="x",
        rel_type="regulates",
        tgt="y",
        w_delta=0.2,
        r_delta=0.5,
        u_delta=-0.1,
        provenance="experiment",
    )
    k.step(events=[event])
    edge = k.edges["e1"]
    assert edge.w > 0.1          # w ökat
    assert edge.r > 0.0          # r jolted
    assert edge.u < 0.8          # u minskat


def test_crystallization():
    """Kanter med w > 0.55 och u < 0.35 kristalliserar."""
    k = nouse.Kernel(w_threshold=0.55, u_ceiling=0.35)
    k.upsert_edge("strong", src="a", rel_type="enables", tgt="b", w=0.8, u=0.1)
    k.upsert_edge("weak", src="c", rel_type="enables", tgt="d", w=0.2, u=0.9)
    crystallized = k.crystallize()
    ids = [e.edge_id for e in crystallized]
    assert "strong" in ids
    assert "weak" not in ids
    assert k.edges["strong"].crystallized is True
    assert k.edges["weak"].crystallized is False


def test_save_load_roundtrip(tmp_path):
    """Brain image kan sparas och laddas utan förlust av strukturella data."""
    k = nouse.Kernel()
    k.add_node("n1", node_type="concept", label="Test",
               states={"a": 0.6, "b": 0.4}, uncertainty=0.3,
               evidence_score=0.5, goal_weight=0.1, attrs={})
    k.upsert_edge("e1", src="n1", rel_type="analog_to", tgt="n2",
                  w=0.6, r=0.0, u=0.2, provenance="roundtrip_test")
    path = str(tmp_path / "brain.json")
    k.save(path)

    k2 = nouse.Kernel.load(path)
    node = k2.nodes.get("n1")
    edge = k2.edges.get("e1")
    assert node is not None
    assert edge is not None
    assert abs(edge.w - 0.6) < 1e-9
