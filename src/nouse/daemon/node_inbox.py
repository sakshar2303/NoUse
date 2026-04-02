"""
NodeInbox — Arbetsminne (Hippocampus)
======================================

12-timmars rullande lista över nya noder och relationer.
Fungerar som episodiskt arbetsminne innan konsolidering.

Analogt med hippocampus:
  - Snabb inlagring (alla källor, hög plasticitet)
  - Episodiskt + kontextbundet (vet VAR och NÄR)
  - Glöms utan konsolidering (NightRun)
  - Replay under NightRun → konsolideras till FieldSurface

Struktur per entry:
  {
    "id":           uuid,
    "ts":           ISO-timestamp,
    "src":          "mesoscale_eddy",
    "rel_type":     "orsakar",
    "tgt":          "heat_flux_anomaly",
    "why":          "...",
    "domain_src":   "oceanografi",
    "domain_tgt":   "oceanografi",
    "evidence_score": 0.82,
    "source":       "curiosity_loop / file / telegram / ...",
    "context_ptr":  "/path/till/källfil eller session-id",
    "consolidated": false
  }

Filen roteras var 12:e timme.
Daemonen och LLM kan läsa den direkt för "vad är nytt?".
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

_log = logging.getLogger("nouse.inbox")

INBOX_DIR  = Path.home() / ".local" / "share" / "nouse" / "inbox"
WINDOW_SEC = 12 * 3600   # 12 timmar


# ── Datamodell ────────────────────────────────────────────────────────────────

@dataclass
class InboxEntry:
    id:             str
    ts:             str        # ISO 8601
    src:            str
    rel_type:       str
    tgt:            str
    why:            str
    domain_src:     str
    domain_tgt:     str
    evidence_score: float
    source:         str        # varifrån kom det
    context_ptr:    str        # session-id, filsökväg, URL
    consolidated:   bool = False

    @classmethod
    def from_relation(
        cls,
        src: str,
        rel_type: str,
        tgt: str,
        *,
        why: str = "",
        domain_src: str = "okänd",
        domain_tgt: str = "okänd",
        evidence_score: float = 0.35,
        source: str = "unknown",
        context_ptr: str = "",
    ) -> "InboxEntry":
        return cls(
            id=str(uuid.uuid4()),
            ts=datetime.now(timezone.utc).isoformat(),
            src=src,
            rel_type=rel_type,
            tgt=tgt,
            why=why,
            domain_src=domain_src,
            domain_tgt=domain_tgt,
            evidence_score=evidence_score,
            source=source,
            context_ptr=context_ptr,
            consolidated=False,
        )


# ── Inbox ─────────────────────────────────────────────────────────────────────

class NodeInbox:
    """
    Skriv- och läsgränssnitt mot arbetsminnet.

    Trådsäker via atomisk fil-append (en rad = en JSON-post).
    Läsning returnerar bara poster inom aktuellt 12h-fönster.
    """

    def __init__(self, inbox_dir: Path | str | None = None):
        self._dir = Path(inbox_dir) if inbox_dir else INBOX_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _current_file(self) -> Path:
        """En fil per 12h-period: inbox_YYYYMMDD_HH.jsonl (00 eller 12)."""
        now = datetime.now(timezone.utc)
        half = "00" if now.hour < 12 else "12"
        return self._dir / f"inbox_{now.strftime('%Y%m%d')}_{half}.jsonl"

    def append(self, entry: InboxEntry) -> None:
        """Skriv en ny post till aktuell inbox-fil (atomic append)."""
        line = json.dumps(asdict(entry), ensure_ascii=False) + "\n"
        with open(self._current_file(), "a", encoding="utf-8") as f:
            f.write(line)

    def add(
        self,
        src: str,
        rel_type: str,
        tgt: str,
        **kwargs,
    ) -> InboxEntry:
        """Skapa och spara en ny entry. Returnerar entry."""
        entry = InboxEntry.from_relation(src, rel_type, tgt, **kwargs)
        self.append(entry)
        return entry

    def read_window(self, window_sec: int = WINDOW_SEC) -> list[InboxEntry]:
        """Returnera alla okonsoliderade poster inom fönstret."""
        cutoff = time.time() - window_sec
        entries: list[InboxEntry] = []

        for f in sorted(self._dir.glob("inbox_*.jsonl")):
            # Hoppa över gamla filer baserat på filnamn (snabb pre-filter)
            try:
                fname = f.stem  # inbox_20260402_00
                parts = fname.split("_")
                date_str = parts[1]
                hour_str = parts[2]
                file_ts = datetime.strptime(
                    f"{date_str} {hour_str}:00:00", "%Y%m%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc).timestamp()
                if file_ts + WINDOW_SEC < cutoff:
                    continue
            except (IndexError, ValueError):
                pass

            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    ts = datetime.fromisoformat(d["ts"]).timestamp()
                    if ts < cutoff:
                        continue
                    if d.get("consolidated"):
                        continue
                    entries.append(InboxEntry(**d))
            except Exception as e:
                _log.warning("Kunde inte läsa inbox-fil %s: %s", f, e)

        return entries

    def mark_consolidated(self, entry_ids: set[str]) -> int:
        """Markera poster som konsoliderade. Returnerar antal uppdaterade."""
        if not entry_ids:
            return 0
        updated = 0
        for f in self._dir.glob("inbox_*.jsonl"):
            lines = []
            changed = False
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if d.get("id") in entry_ids and not d.get("consolidated"):
                        d["consolidated"] = True
                        changed = True
                        updated += 1
                    lines.append(json.dumps(d, ensure_ascii=False))
                if changed:
                    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except Exception as e:
                _log.warning("mark_consolidated fel på %s: %s", f, e)
        return updated

    def summary(self, window_sec: int = WINDOW_SEC) -> dict:
        """Snabb sammanfattning för LLM/CLI: vad är nytt?"""
        entries = self.read_window(window_sec)
        by_source: dict[str, int] = {}
        by_domain: dict[str, int] = {}
        for e in entries:
            by_source[e.source] = by_source.get(e.source, 0) + 1
            by_domain[e.domain_src] = by_domain.get(e.domain_src, 0) + 1
        return {
            "total_new": len(entries),
            "window_hours": window_sec // 3600,
            "by_source": by_source,
            "by_domain": by_domain,
            "top_nodes": _top_nodes(entries, n=10),
            "unconsolidated": sum(1 for e in entries if not e.consolidated),
        }

    def prune_old(self, keep_days: int = 7) -> int:
        """Ta bort inbox-filer äldre än keep_days. Returnerar antal borttagna."""
        cutoff = time.time() - keep_days * 86400
        removed = 0
        for f in self._dir.glob("inbox_*.jsonl"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        return removed


def _top_nodes(entries: list[InboxEntry], n: int = 10) -> list[dict]:
    """Noder som förekommer flest gånger i inboxen."""
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.src] = counts.get(e.src, 0) + 1
        counts[e.tgt] = counts.get(e.tgt, 0) + 1
    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]
    return [{"node": k, "count": v} for k, v in top]


# ── Global singleton ──────────────────────────────────────────────────────────

_inbox: NodeInbox | None = None

def get_inbox() -> NodeInbox:
    global _inbox
    if _inbox is None:
        _inbox = NodeInbox()
    return _inbox
