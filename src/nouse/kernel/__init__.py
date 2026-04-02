"""
nouse.kernel — Residual Stream brain engine (formerly brain-db-core).

Core innovation: three-channel (w, r, u) residual streams per edge.
  w = crystallized weight (long-term potentiation)
  r = recent/episodic signal (decays, tau ~89%)
  u = uncertainty/inhibition

path_signal = w + 0.45*r - 0.25*u
"""
from .brain import Brain, FieldEvent, NeuromodulatorState, NodeStateSpace, ResidualEdge
from .db import ArchivedEdgeRecord, BrainDB, ResidualEdgeState
from .schema import SCHEMA_VERSION, MEMORY_TIERS, NEUROMODULATORS

__all__ = [
    "Brain",
    "FieldEvent",
    "NodeStateSpace",
    "ResidualEdge",
    "NeuromodulatorState",
    "BrainDB",
    "ResidualEdgeState",
    "ArchivedEdgeRecord",
    "SCHEMA_VERSION",
    "MEMORY_TIERS",
    "NEUROMODULATORS",
]
