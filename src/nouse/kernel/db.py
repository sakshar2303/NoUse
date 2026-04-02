from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import kuzu  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    kuzu = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _quote(value: str) -> str:
    return value.replace("'", "''")


@dataclass
class ResidualEdgeState:
    edge_id: str
    src: str
    rel_type: str
    tgt: str
    w: float = 0.02
    r: float = 0.0
    u: float = 0.80
    evidence_score: float = 0.0
    provenance: str = "unknown"
    created_at: str = ""
    last_snapshot_cycle: int = -1
    last_snapshot_r: float = 0.0
    last_snapshot_w: float = 0.0
    last_snapshot_u: float = 0.0

    def __post_init__(self) -> None:
        self.w = _clamp(self.w, 0.0, 1.0)
        self.u = _clamp(self.u, 0.0, 1.0)
        self.r = _clamp(self.r, -2.0, 2.0)
        self.evidence_score = _clamp(self.evidence_score, 0.0, 1.0)
        if not self.created_at:
            self.created_at = _now_iso()


@dataclass
class ArchivedEdgeRecord:
    edge_id: str
    src: str
    rel_type: str
    tgt: str
    w: float
    u: float
    evidence_score: float
    provenance: str
    created_at: str
    updated_at: str
    crystallized_at: str | None = None
    snapshot_cycle: int | None = None
    snapshot_reason: str = "manual"


class BrainDB:
    """Two-plane Brain DB:

    - Live plane (in memory): ResidualEdgeState with dynamic `r`.
    - Persistent plane (archive): canonical `w`, `u`, evidence, provenance.

    `r` is intentionally live-primary and not canonical persistent state.
    """

    def __init__(
        self,
        kuzu_path: str | Path,
        *,
        w_threshold: float = 0.60,
        u_ceiling: float = 0.40,
        r_decay: float = 0.89,
        snapshot_interval: int = 25,
        r_delta_snapshot: float = 0.30,
        use_kuzu: bool = True,
    ) -> None:
        self.kuzu_path = Path(kuzu_path)
        self.w_threshold = w_threshold
        self.u_ceiling = u_ceiling
        self.r_decay = r_decay
        self.snapshot_interval = max(1, snapshot_interval)
        self.r_delta_snapshot = max(0.0, r_delta_snapshot)

        self._cycle = 0
        self._live: dict[str, ResidualEdgeState] = {}
        self._archive: dict[str, ArchivedEdgeRecord] = {}

        self._kuzu_conn: Any | None = None
        self._kuzu_write_enabled = False
        self._kuzu_error: str | None = None
        if use_kuzu and kuzu is not None:
            self._init_kuzu()

    @property
    def cycle(self) -> int:
        return self._cycle

    @property
    def kuzu_error(self) -> str | None:
        return self._kuzu_error

    def _init_kuzu(self) -> None:
        self.kuzu_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            db = kuzu.Database(str(self.kuzu_path))
            conn = kuzu.Connection(db)
            self._kuzu_conn = conn
            self._kuzu_write_enabled = True
            self._ensure_schema()
        except Exception as exc:  # pragma: no cover - depends on kuzu runtime
            self._kuzu_error = f"init_failed: {exc}"
            self._kuzu_conn = None
            self._kuzu_write_enabled = False

    def _try_exec(self, query: str) -> bool:
        if not self._kuzu_conn:
            return False
        try:
            self._kuzu_conn.execute(query)
            return True
        except Exception as exc:  # pragma: no cover - depends on kuzu runtime
            self._kuzu_error = f"query_failed: {exc}"
            return False

    def _ensure_schema(self) -> None:
        # Kuzu syntax can vary by version; try conservative variants.
        created_nodes = self._try_exec(
            "CREATE NODE TABLE IF NOT EXISTS BrainNode(node_id STRING, PRIMARY KEY(node_id));"
        )
        if not created_nodes:
            self._try_exec("CREATE NODE TABLE BrainNode(node_id STRING, PRIMARY KEY(node_id));")

        created_rel = self._try_exec(
            "CREATE REL TABLE IF NOT EXISTS ResidualEdge(FROM BrainNode TO BrainNode, edge_id STRING, rel_type STRING, w DOUBLE, u DOUBLE, evidence_score DOUBLE, provenance STRING, created_at STRING, updated_at STRING, crystallized_at STRING, snapshot_cycle INT64, snapshot_reason STRING);"
        )
        if not created_rel:
            self._try_exec(
                "CREATE REL TABLE ResidualEdge(FROM BrainNode TO BrainNode, edge_id STRING, rel_type STRING, w DOUBLE, u DOUBLE, evidence_score DOUBLE, provenance STRING, created_at STRING, updated_at STRING, crystallized_at STRING, snapshot_cycle INT64, snapshot_reason STRING);"
            )

    def upsert_live_edge(
        self,
        edge_id: str,
        *,
        src: str,
        rel_type: str,
        tgt: str,
        w: float = 0.02,
        r: float = 0.0,
        u: float = 0.80,
        evidence_score: float = 0.0,
        provenance: str = "unknown",
    ) -> ResidualEdgeState:
        st = ResidualEdgeState(
            edge_id=edge_id,
            src=src,
            rel_type=rel_type,
            tgt=tgt,
            w=w,
            r=r,
            u=u,
            evidence_score=evidence_score,
            provenance=provenance,
        )
        self._live[edge_id] = st
        return st

    def get_live_edge(self, edge_id: str) -> ResidualEdgeState | None:
        return self._live.get(edge_id)

    def update_live_edge(
        self,
        edge_id: str,
        *,
        w_delta: float = 0.0,
        r_delta: float = 0.0,
        u_delta: float = 0.0,
        evidence_score: float | None = None,
        provenance: str | None = None,
    ) -> ResidualEdgeState:
        st = self._live[edge_id]
        st.w = _clamp(st.w + w_delta, 0.0, 1.0)
        st.r = _clamp(st.r + r_delta, -2.0, 2.0)
        st.u = _clamp(st.u + u_delta, 0.0, 1.0)
        if evidence_score is not None:
            st.evidence_score = _clamp(evidence_score, 0.0, 1.0)
        if provenance is not None:
            st.provenance = provenance
        return st

    def advance_cycle(self, cycles: int = 1) -> None:
        for _ in range(max(1, cycles)):
            self._cycle += 1
            for st in self._live.values():
                st.r = _clamp(st.r * self.r_decay, -2.0, 2.0)
            if any(self._should_snapshot(st) for st in self._live.values()):
                self.snapshot(force=False, reason="auto")

    def _should_snapshot(self, st: ResidualEdgeState) -> bool:
        if st.last_snapshot_cycle < 0:
            return True
        if self._cycle - st.last_snapshot_cycle >= self.snapshot_interval:
            return True
        if abs(st.r - st.last_snapshot_r) >= self.r_delta_snapshot:
            return True
        return False

    def crystallize_edge(self, edge_id: str) -> bool:
        st = self._live[edge_id]
        if st.w > self.w_threshold and st.u < self.u_ceiling:
            rec = ArchivedEdgeRecord(
                edge_id=st.edge_id,
                src=st.src,
                rel_type=st.rel_type,
                tgt=st.tgt,
                w=st.w,
                u=st.u,
                evidence_score=st.evidence_score,
                provenance=st.provenance,
                created_at=st.created_at,
                updated_at=_now_iso(),
                crystallized_at=_now_iso(),
                snapshot_cycle=self._cycle,
                snapshot_reason="crystallize",
            )
            self._write_archive(rec)
            st.last_snapshot_cycle = self._cycle
            st.last_snapshot_w = st.w
            st.last_snapshot_u = st.u
            st.last_snapshot_r = st.r
            return True
        return False

    def snapshot(self, *, force: bool = False, reason: str = "manual") -> int:
        written = 0
        for st in self._live.values():
            if not force and not self._should_snapshot(st):
                continue
            rec = ArchivedEdgeRecord(
                edge_id=st.edge_id,
                src=st.src,
                rel_type=st.rel_type,
                tgt=st.tgt,
                w=st.w,
                u=st.u,
                evidence_score=st.evidence_score,
                provenance=st.provenance,
                created_at=st.created_at,
                updated_at=_now_iso(),
                crystallized_at=None,
                snapshot_cycle=self._cycle,
                snapshot_reason=reason,
            )
            self._write_archive(rec)
            st.last_snapshot_cycle = self._cycle
            st.last_snapshot_w = st.w
            st.last_snapshot_u = st.u
            st.last_snapshot_r = st.r
            written += 1
        return written

    def shutdown(self) -> int:
        return self.snapshot(force=True, reason="shutdown")

    def get_archived_edge(self, edge_id: str) -> ArchivedEdgeRecord | None:
        return self._archive.get(edge_id)

    def iter_archived_edges(self) -> list[ArchivedEdgeRecord]:
        return list(self._archive.values())

    def _write_archive(self, rec: ArchivedEdgeRecord) -> None:
        self._archive[rec.edge_id] = rec
        self._write_kuzu_record(rec)

    def _write_kuzu_record(self, rec: ArchivedEdgeRecord) -> None:
        if not self._kuzu_conn or not self._kuzu_write_enabled:
            return
        # Best-effort Kuzu persistence; local in-memory archive remains canonical
        # in environments where Kuzu syntax/runtime differs.
        q_src = _quote(rec.src)
        q_tgt = _quote(rec.tgt)
        q_id = _quote(rec.edge_id)
        q_rel = _quote(rec.rel_type)
        q_prov = _quote(rec.provenance)
        q_created = _quote(rec.created_at)
        q_updated = _quote(rec.updated_at)
        q_cr = _quote(rec.crystallized_at or "")
        q_reason = _quote(rec.snapshot_reason)
        snapshot_cycle = rec.snapshot_cycle if rec.snapshot_cycle is not None else -1
        queries = [
            f"MERGE (n:BrainNode {{node_id: '{q_src}'}});",
            f"MERGE (n:BrainNode {{node_id: '{q_tgt}'}});",
            (
                "MATCH (s:BrainNode {node_id: '"
                + q_src
                + "'}), (t:BrainNode {node_id: '"
                + q_tgt
                + "'}) "
                + "MERGE (s)-[e:ResidualEdge {edge_id: '"
                + q_id
                + "'}]->(t) "
                + "SET e.rel_type = '"
                + q_rel
                + "', "
                + f"e.w = {rec.w}, e.u = {rec.u}, e.evidence_score = {rec.evidence_score}, "
                + "e.provenance = '"
                + q_prov
                + "', e.created_at = '"
                + q_created
                + "', e.updated_at = '"
                + q_updated
                + "', e.crystallized_at = '"
                + q_cr
                + f"', e.snapshot_cycle = {snapshot_cycle}, "
                + "e.snapshot_reason = '"
                + q_reason
                + "';"
            ),
        ]
        for query in queries:
            if not self._try_exec(query):
                self._kuzu_write_enabled = False
                break
