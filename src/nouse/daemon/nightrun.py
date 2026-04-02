"""
NightRun — Konsolidering (Slow-Wave Sleep)
==========================================

Bearbetar NodeInbox → konsoliderar till FieldSurface.

Analogt med hippocampal replay under sömn:
  1. Replay: läs alla okonsoliderade inbox-poster
  2. Evaluera: är evidensen tillräcklig?
  3. Konsolidera: starka noder → permanent i FieldSurface
  4. Kasta: svaga noder → kasseras (eller behåller assumption_flag)
  5. Bisociation: leta korsdomän-kopplingar i nya noder
  6. Pruning: rensa svaga gamla kanter

Schema (konfigureras av användaren):
  "idle:N"  → kör om ingen aktivitet på N minuter
  "night"   → kör 22:00–06:00
  "always"  → kör kontinuerligt (kräver stor hårdvara)
  "never"   → manuellt via: b76 nightrun now

Konfigurationsfil: ~/.local/share/nouse/nightrun_config.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

_log = logging.getLogger("nouse.nightrun")

CONFIG_FILE  = Path.home() / ".local" / "share" / "b76" / "nightrun_config.json"
STATUS_FILE  = Path.home() / ".local" / "share" / "b76" / "nightrun_status.json"

# Konsoliderings-trösklar
CONSOLIDATION_MIN_EVIDENCE  = float(os.getenv("NOUSE_NIGHTRUN_MIN_EVIDENCE",  "0.45"))
CONSOLIDATION_MIN_SUPPORT   = int(os.getenv("NOUSE_NIGHTRUN_MIN_SUPPORT",     "1"))
STRONG_CONSOLIDATION        = float(os.getenv("NOUSE_NIGHTRUN_STRONG_EVIDENCE","0.65"))

NightRunMode = Literal["idle", "night", "always", "never"]


# ── Konfiguration ─────────────────────────────────────────────────────────────

@dataclass
class NightRunConfig:
    mode:          NightRunMode = "idle"
    idle_minutes:  int   = 30       # för mode="idle"
    night_start:   int   = 22       # timme 0–23
    night_end:     int   = 6        # timme 0–23
    max_runtime_minutes: int = 60   # maximal körtid per session

    def save(self) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> "NightRunConfig":
        if CONFIG_FILE.exists():
            try:
                return cls(**json.loads(CONFIG_FILE.read_text()))
            except Exception:
                pass
        return cls()

    def should_run_now(self, last_activity_ts: float) -> bool:
        now = datetime.now(timezone.utc)
        if self.mode == "never":
            return False
        if self.mode == "always":
            return True
        if self.mode == "idle":
            idle_sec = time.time() - last_activity_ts
            return idle_sec >= self.idle_minutes * 60
        if self.mode == "night":
            h = now.hour
            if self.night_start > self.night_end:
                return h >= self.night_start or h < self.night_end
            return self.night_start <= h < self.night_end
        return False


@dataclass
class NightRunStatus:
    last_run_ts:        float = 0.0
    last_run_duration:  float = 0.0
    total_consolidated: int   = 0
    total_discarded:    int   = 0
    total_bisociations: int   = 0
    total_pruned:       int   = 0
    last_error:         str   = ""

    def save(self) -> None:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> "NightRunStatus":
        if STATUS_FILE.exists():
            try:
                return cls(**json.loads(STATUS_FILE.read_text()))
            except Exception:
                pass
        return cls()


# ── Konsolideringslogik ───────────────────────────────────────────────────────

@dataclass
class ConsolidationResult:
    consolidated:    int = 0
    discarded:       int = 0
    bisociations:    int = 0
    pruned:          int = 0
    enriched:        int = 0    # noder berikat med kontext
    axioms_committed: int = 0   # axiom från deepdive som skrevs direkt
    axioms_flagged:  int = 0    # axiom flaggade för vidare granskning
    reviews_promoted: int = 0   # flaggade axiom som befordrades via deep review
    reviews_discarded: int = 0  # flaggade axiom som kasserades via deep review
    duration:        float = 0.0


async def run_night_consolidation(
    field,         # FieldSurface
    inbox,         # NodeInbox
    limbic,        # LimbicState
    *,
    max_minutes: int = 60,
    dry_run: bool = False,
) -> ConsolidationResult:
    """
    Huvudfunktion för NightRun-konsolidering.

    1. Hämta okonsoliderade inbox-poster
    2. Evaluera evidens per relation
    3. Konsolidera starka → mark as consolidated
    4. Kasta svaga (lämnar dem unconsolidated = glöms)
    5. Bisociation-pass på nya noder
    6. Pruning av svaga gamla kanter
    """
    from nouse.orchestrator.compaction import should_run, run_compaction
    from nouse.learning_coordinator import LearningCoordinator
    from nouse.daemon.storage_tier import get_tier

    tier_limits = get_tier().limits()
    min_evidence = tier_limits.nightrun_min_evidence   # respekterar small/medium/large

    t0 = time.monotonic()
    deadline = t0 + max_minutes * 60
    result = ConsolidationResult()

    coordinator = LearningCoordinator(field, limbic)
    entries = inbox.read_window()

    if not entries:
        _log.info("NightRun: inbox tom — inget att konsolidera")
        return result

    _log.info("NightRun: %d okonsoliderade poster att bearbeta", len(entries))

    consolidated_ids: set[str] = set()

    # ── Steg 1+2+3: Evaluera och konsolidera ──────────────────────────────────
    for entry in entries:
        if time.monotonic() > deadline:
            _log.warning("NightRun: tidsgräns nådd (%d min)", max_minutes)
            break

        ev = entry.evidence_score

        if ev >= min_evidence:
            # Stärk kanten i grafen — med evidens-skalat delta
            if not dry_run:
                coordinator.on_fact(
                    entry.src, entry.rel_type, entry.tgt,
                    why=entry.why,
                    evidence_score=ev,
                    support_count=CONSOLIDATION_MIN_SUPPORT,
                )
            consolidated_ids.add(entry.id)
            result.consolidated += 1
            _log.debug(
                "Konsoliderar: %s─[%s]→%s  ev=%.2f",
                entry.src, entry.rel_type, entry.tgt, ev
            )
        else:
            # Svag evidens — lämna unconsolidated, den försvinner vid prune_old()
            result.discarded += 1
            _log.debug(
                "Kasserar (ev=%.2f < %.2f): %s→%s",
                ev, CONSOLIDATION_MIN_EVIDENCE, entry.src, entry.tgt
            )

        await asyncio.sleep(0)  # yield till event loop

    # ── Steg 4: Markera konsoliderade ────────────────────────────────────────
    if not dry_run and consolidated_ids:
        inbox.mark_consolidated(consolidated_ids)

    # ── Steg 5: Bisociation-pass på nya noder ─────────────────────────────────
    new_nodes = {e.src for e in entries} | {e.tgt for e in entries}
    new_domains = {e.domain_src for e in entries} | {e.domain_tgt for e in entries}

    if len(new_domains) >= 2 and not dry_run:
        domain_list = list(new_domains)
        for i, da in enumerate(domain_list):
            for db in domain_list[i+1:]:
                if time.monotonic() > deadline:
                    break
                try:
                    path = field.find_path(da, db, max_hops=5)
                    if path:
                        result.bisociations += 1
                        _log.info(
                            "NightRun bisociation: %s ↔ %s (%d hopp)",
                            da, db, len(path)
                        )
                except Exception:
                    pass
                await asyncio.sleep(0)

    # ── Steg 6: Pruning ───────────────────────────────────────────────────────
    if not dry_run and should_run(0):
        try:
            pruned = run_compaction(field)
            result.pruned = pruned
        except Exception as e:
            _log.warning("NightRun pruning misslyckades: %s", e)

    # ── Steg 7: Nod-kontext-berikning (medium/large tier) ─────────────────────
    if not dry_run and time.monotonic() < deadline:
        try:
            from nouse.daemon.node_context import enrich_nodes
            remaining_min = (deadline - time.monotonic()) / 60
            enrich_result = await enrich_nodes(
                field,
                max_nodes=100,
                max_minutes=min(remaining_min, 15.0),
            )
            result.enriched = enrich_result.enriched
        except Exception as e:
            _log.warning("NightRun nod-berikning misslyckades: %s", e)

    # ── Steg 8: Indikerade granskning — ReviewQueue flush ─────────────────────
    # Flaggade axiom som nått REVIEW_INDICATION_THRESHOLD granskas djupare.
    # Utfall: PROMOTE (stärks), KEEP (stannar flaggad), DISCARD (kasseras).
    if not dry_run and time.monotonic() < deadline:
        try:
            from nouse.daemon.node_deepdive import get_review_queue, REVIEW_PROMOTE, REVIEW_DISCARD
            rq = get_review_queue()
            pending = rq.pending_count()
            if pending:
                _log.info("NightRun [8/9] ReviewQueue: %d väntande granskningar", pending)
                remaining_min = (deadline - time.monotonic()) / 60
                max_reviews = max(1, min(pending, int(remaining_min / 2)))
                verdicts = await rq.flush_pending(
                    field,
                    max_reviews=max_reviews,
                    dry_run=dry_run,
                )
                for v in verdicts:
                    if v.outcome == REVIEW_PROMOTE:
                        result.reviews_promoted += 1
                    elif v.outcome == REVIEW_DISCARD:
                        result.reviews_discarded += 1
                _log.info(
                    "NightRun [8/9] ReviewQueue klar: promoted=%d discarded=%d kept=%d",
                    result.reviews_promoted,
                    result.reviews_discarded,
                    len(verdicts) - result.reviews_promoted - result.reviews_discarded,
                )
        except Exception as e:
            _log.warning("NightRun ReviewQueue flush misslyckades: %s", e)

    # ── Steg 9: DeepDive — axiom-discovery på top-N noder ─────────────────────
    # Körs på noder med hög gradtal men svag faktabas.
    # Starka axiom skrivs direkt; svaga hamnar i ReviewQueue för steg 8 nästa cykel.
    if not dry_run and time.monotonic() < deadline:
        try:
            from nouse.daemon.node_deepdive import deepdive_batch
            remaining_min = (deadline - time.monotonic()) / 60
            if remaining_min >= 2.0:
                _log.info("NightRun [9/9] DeepDive: %.1f min kvar", remaining_min)
                batch = await deepdive_batch(
                    field,
                    max_nodes=10,
                    max_minutes=min(remaining_min * 0.8, 20.0),
                    dry_run=dry_run,
                )
                result.axioms_committed = batch.total_committed
                result.axioms_flagged   = batch.total_flagged
                _log.info(
                    "NightRun [9/9] DeepDive klar: noder=%d committed=%d flagged=%d",
                    batch.nodes_processed, batch.total_committed, batch.total_flagged,
                )
        except Exception as e:
            _log.warning("NightRun DeepDive misslyckades: %s", e)

    result.duration = round(time.monotonic() - t0, 2)
    _log.info(
        "NightRun klar: konsoliderat=%d kasserat=%d bisociationer=%d pruning=%d "
        "berikat=%d axiom_committed=%d axiom_flagged=%d "
        "reviews_promoted=%d reviews_discarded=%d (%.1fs)",
        result.consolidated, result.discarded,
        result.bisociations, result.pruned, result.enriched,
        result.axioms_committed, result.axioms_flagged,
        result.reviews_promoted, result.reviews_discarded,
        result.duration,
    )
    return result


# ── Schema-vakt (körs i daemon-loop) ─────────────────────────────────────────

class NightRunScheduler:
    """
    Körs som bakgrundsuppgift i brain_loop.
    Kollar om NightRun ska triggas baserat på config.
    """

    def __init__(self):
        self.config = NightRunConfig.load()
        self.status = NightRunStatus.load()
        self._running = False
        self._last_activity = time.time()

    def touch_activity(self) -> None:
        """Anropa vid varje användarinteraktion (chat, ingest etc.)."""
        self._last_activity = time.time()

    def reload_config(self) -> None:
        self.config = NightRunConfig.load()

    @property
    def is_running(self) -> bool:
        return self._running

    async def maybe_run(
        self,
        field,
        inbox,
        limbic,
    ) -> ConsolidationResult | None:
        """
        Anropa regelbundet från brain_loop (t.ex. var 5:e minut).
        Kör NightRun om schemat säger det — annars noop.
        """
        if self._running:
            return None

        # Ladda om config om den ändrats
        self.reload_config()

        if not self.config.should_run_now(self._last_activity):
            return None

        # Minst 30 min sedan senaste körning
        if time.time() - self.status.last_run_ts < 1800:
            return None

        self._running = True
        _log.info(
            "NightRun startar (mode=%s, idle=%.0fmin)",
            self.config.mode,
            (time.time() - self._last_activity) / 60,
        )

        try:
            result = await run_night_consolidation(
                field, inbox, limbic,
                max_minutes=self.config.max_runtime_minutes,
            )
            self.status.last_run_ts        = time.time()
            self.status.last_run_duration  = result.duration
            self.status.total_consolidated += result.consolidated
            self.status.total_discarded    += result.discarded
            self.status.total_bisociations += result.bisociations
            self.status.total_pruned       += result.pruned
            self.status.last_error         = ""
            self.status.save()
            return result
        except Exception as e:
            self.status.last_error = str(e)
            self.status.save()
            _log.error("NightRun fel: %s", e)
            return None
        finally:
            self._running = False
