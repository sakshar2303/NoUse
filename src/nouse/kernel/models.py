from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrainNode:
    node_id: str
    node_type: str
    label: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainEdge:
    src: str
    rel_type: str
    tgt: str
    evidence_score: float = 0.0
    attrs: dict[str, Any] = field(default_factory=dict)
