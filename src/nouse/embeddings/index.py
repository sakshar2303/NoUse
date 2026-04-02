from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path

import numpy as np


DEFAULT_INDEX_FILE = "chunks.jsonl"


@dataclass
class SearchHit:
    score: float
    path: str
    chunk_ix: int
    text: str
    source: str
    domain_hint: str


def _default_index_path() -> Path:
    root = os.getenv("NOUSE_EMBED_INDEX_PATH", "~/.local/share/nouse/embeddings")
    base = Path(root).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    return base / DEFAULT_INDEX_FILE


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n <= 0:
        return v
    return v / n


class JsonlVectorIndex:
    def __init__(self, path: Path | None = None):
        self.path = path or _default_index_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add_records(self, records: list[dict]) -> int:
        if not records:
            return 0
        with self.path.open("a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return len(records)

    def iter_records(self):
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def make_chunk_record(
    *,
    path: str,
    chunk_ix: int,
    text: str,
    vector: list[float],
    source: str,
    domain_hint: str,
) -> dict:
    chunk_id = sha1(f"{path}|{chunk_ix}|{text[:200]}".encode("utf-8", errors="ignore")).hexdigest()
    return {
        "id": chunk_id,
        "path": path,
        "chunk_ix": int(chunk_ix),
        "text": text,
        "vector": vector,
        "source": source,
        "domain_hint": domain_hint,
    }


def search_index(
    *,
    query_vector: list[float],
    top_k: int = 5,
    index_path: Path | None = None,
) -> list[SearchHit]:
    idx = JsonlVectorIndex(index_path)
    q = _normalize(np.asarray(query_vector, dtype=np.float32))
    hits: list[SearchHit] = []

    for rec in idx.iter_records() or []:
        vec = rec.get("vector")
        if not isinstance(vec, list) or not vec:
            continue
        v = _normalize(np.asarray(vec, dtype=np.float32))
        if v.shape != q.shape:
            continue
        score = float(np.dot(q, v))
        hits.append(
            SearchHit(
                score=score,
                path=str(rec.get("path") or ""),
                chunk_ix=int(rec.get("chunk_ix") or 0),
                text=str(rec.get("text") or ""),
                source=str(rec.get("source") or ""),
                domain_hint=str(rec.get("domain_hint") or ""),
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[: max(1, int(top_k))]
