"""
b76.tda.bridge — Python-brygga till Rust TDA-motorn
=====================================================
Beräknar Betti-nummer (H0, H1) och topologisk similaritet
via den kompilerade Rust-modulen tda_engine.

Fabrikslogik:
  1. Försöker importera tda_engine (Rust, snabb)
  2. Fallback: Python-implementation (scipy, långsam men fungerar)

Bygga Rust-modulen:
  cd /home/bjorn/projects/nouse/crates/tda_engine
  maturin develop --release -m /home/bjorn/projects/nouse/crates/tda_engine/Cargo.toml

Eller via install.sh (görs automatiskt).
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

log = logging.getLogger("nouse.tda")

# Försök Rust-modulen
_RUST_AVAILABLE = False
try:
    import tda_engine as _tda  # type: ignore[import]
    _RUST_AVAILABLE = True
    log.info("TDA: Rust-motor aktiv (tda_engine)")
except ImportError:
    log.warning("TDA: Rust-motor saknas — faller tillbaka till Python. "
                "Kör: cd crates/tda_engine && maturin develop --release")


# ── Publikt API ──────────────────────────────────────────────────────────────

def compute_distance_matrix(embeddings: list[list[float]]) -> list[list[float]]:
    """Beräkna euklidisk distansmatris från embeddings."""
    if _RUST_AVAILABLE:
        return _tda.compute_distance_matrix(embeddings)
    return _py_distance_matrix(embeddings)


def compute_betti(
    dist_matrix: list[list[float]],
    max_epsilon: float = 2.0,
    steps: int = 50,
) -> tuple[int, int]:
    """
    Beräkna Betti-nummer H0 och H1.
    
    H0 = antal sammanhängande komponenter
    H1 = antal oberoende cykler
    
    Returerar (h0, h1).
    """
    if _RUST_AVAILABLE:
        return _tda.compute_betti(dist_matrix, max_epsilon, steps)
    return _py_betti(dist_matrix, max_epsilon)


def topological_similarity(
    h0_a: int, h1_a: int,
    h0_b: int, h1_b: int,
) -> float:
    """
    Topologisk similaritet [0.0, 1.0] baserat på Betti-profiler.
    Hög τ + låg semantisk likhet → potentiell bisociation!
    """
    if _RUST_AVAILABLE:
        return _tda.topological_similarity(h0_a, h1_a, h0_b, h1_b)
    return _py_topological_similarity(h0_a, h1_a, h0_b, h1_b)


def is_rust_active() -> bool:
    """Returnerar True om Rust TDA-motorn är laddad."""
    return _RUST_AVAILABLE


# ── Python-fallback ──────────────────────────────────────────────────────────

def _py_distance_matrix(embeddings: list[list[float]]) -> list[list[float]]:
    n = len(embeddings)
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(embeddings[i], embeddings[j])))
            dist[i][j] = d
            dist[j][i] = d
    return dist


def _py_betti(dist_matrix: list[list[float]], max_epsilon: float) -> tuple[int, int]:
    n = len(dist_matrix)
    if n < 2:
        return (n, 0)

    # Samla kanter sorterade
    edges = sorted(
        [(dist_matrix[i][j], i, j) for i in range(n) for j in range(i + 1, n)],
        key=lambda e: e[0],
    )

    parent = list(range(n))
    rank   = [0] * n
    h0 = n
    h1 = 0

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for dist, u, v in edges:
        if dist > max_epsilon:
            break
        pu, pv = find(u), find(v)
        if pu == pv:
            h1 += 1
        else:
            if rank[pu] < rank[pv]:
                parent[pu] = pv
            elif rank[pu] > rank[pv]:
                parent[pv] = pu
            else:
                parent[pv] = pu
                rank[pu] += 1
            h0 = max(1, h0 - 1)

    return (h0, h1)


def _py_topological_similarity(h0_a: int, h1_a: int, h0_b: int, h1_b: int) -> float:
    dh0 = abs(h0_a - h0_b)
    dh1 = abs(h1_a - h1_b)
    max_h0 = max(h0_a, h0_b)
    max_h1 = max(h1_a, h1_b)
    norm_h0 = 1.0 - dh0 / max_h0 if max_h0 > 0 else 1.0
    norm_h1 = 1.0 - dh1 / max_h1 if max_h1 > 0 else 1.0
    return max(0.0, min(1.0, 0.35 * norm_h0 + 0.65 * norm_h1))
