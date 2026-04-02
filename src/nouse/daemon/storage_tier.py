"""
StorageTier — Lagringsprofiler för Nouse
=========================================

Tre nivåer som styr hur mycket hårddisk Nouse använder och
hur djupt varje nod indexeras.

  small   — Bara nodgraf + relationer. Snabb start, låg förbrukning.
             LLM hämtar kontext live från internet/cloud.
             Passar: laptop, testmiljö, begränsad disk.

  medium  — Noder + relationer + kontext-snippet per nod (≤2 KB).
             LLM hämtar detaljerad knowledge online eller från extern
             cloud-DB (Qdrant, Pinecone etc.) vid behov.
             Passar: skrivbord/researcher, normal användning.

  large   — Hel hårddisk indexeras som NN (minus systemfiler/installationer).
             Allt lagras lokalt — ingen extern beroenden.
             Passar: airgap, enterprise, dedikerat system med stor disk.

Konfigurationsfil: ~/.local/share/nouse/storage_tier.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Literal

_log = logging.getLogger("nouse.storage_tier")

CONFIG_FILE = Path.home() / ".local" / "share" / "nouse" / "storage_tier.json"

TierName = Literal["small", "medium", "large"]


@dataclass
class TierLimits:
    # Hårddisk
    max_db_gb:               float
    max_inbox_mb:            float
    max_trace_mb:            float
    max_episodic_mb:         float
    # Nod-kontext
    context_per_node_chars:  int
    knowledge_per_node_chars: int
    # Scanning
    max_scan_files:          int
    # NightRun
    nightrun_min_evidence:   float
    prune_below_weight:      float
    # Retrieval
    fetch_online:            bool
    cloud_db_url:            str
    # Default-argument sist
    scan_extensions: list[str] = field(default_factory=list)

    def warn_if_approaching(self, current_gb: float) -> str | None:
        threshold = self.max_db_gb * 0.85
        if current_gb >= threshold:
            return (
                f"⚠️  FieldSurface är {current_gb:.1f} GB "
                f"({current_gb/self.max_db_gb*100:.0f}% av {self.max_db_gb} GB-gränsen). "
                f"Överväg att köra 'b76 nightrun now' eller byta till en större tier."
            )
        return None


# ── Tier-definitioner ─────────────────────────────────────────────────────────

TIER_DEFAULTS: dict[TierName, TierLimits] = {
    "small": TierLimits(
        max_db_gb=10.0,
        max_inbox_mb=50.0,
        max_trace_mb=10.0,
        max_episodic_mb=100.0,
        context_per_node_chars=0,       # ingen inbäddad kontext
        knowledge_per_node_chars=0,
        max_scan_files=50_000,
        scan_extensions=[".md", ".txt", ".pdf"],
        nightrun_min_evidence=0.55,     # strikt — pruna mer aggressivt
        prune_below_weight=0.25,
        fetch_online=True,
        cloud_db_url="",
    ),
    "medium": TierLimits(
        max_db_gb=100.0,
        max_inbox_mb=500.0,
        max_trace_mb=50.0,
        max_episodic_mb=500.0,
        context_per_node_chars=2_000,   # 2 KB kontext per nod
        knowledge_per_node_chars=500,
        max_scan_files=500_000,
        scan_extensions=[".md", ".txt", ".pdf", ".py", ".rs", ".ts", ".csv", ".json"],
        nightrun_min_evidence=0.45,
        prune_below_weight=0.15,
        fetch_online=True,
        cloud_db_url="",
    ),
    "large": TierLimits(
        max_db_gb=500.0,
        max_inbox_mb=5_000.0,
        max_trace_mb=200.0,
        max_episodic_mb=5_000.0,
        context_per_node_chars=10_000,  # 10 KB kontext per nod
        knowledge_per_node_chars=5_000,
        max_scan_files=10_000_000,
        scan_extensions=[],             # alla filtyper (minus exkluderade)
        nightrun_min_evidence=0.35,     # tolerant — behåll mer
        prune_below_weight=0.05,
        fetch_online=False,             # airgap-säker
        cloud_db_url="",
    ),
}

TIER_DESCRIPTIONS = {
    "small": (
        "Nodgraf + relationer. LLM hämtar kontext online.\n"
        "  Passar: laptop, testmiljö, begränsad disk (<10 GB)\n"
        "  Kontext per nod: ingen (live-hämtning)\n"
        "  Max filer att skanna: 50 000"
    ),
    "medium": (
        "Noder + relationer + kontext-snippet per nod (2 KB).\n"
        "  Passar: desktop, researcher, normal användning (<100 GB)\n"
        "  Kontext per nod: 2 KB inbäddad + online-fallback\n"
        "  Max filer att skanna: 500 000"
    ),
    "large": (
        "Hela hårddisken som NN (minus system). Airgap-säker.\n"
        "  Passar: enterprise, dedikerat system, offline (<500 GB)\n"
        "  Kontext per nod: 10 KB inbäddad, ingen extern beroende\n"
        "  Max filer att skanna: 10 000 000"
    ),
}


# ── Konfiguration ─────────────────────────────────────────────────────────────

@dataclass
class StorageTierConfig:
    tier: TierName = "medium"
    # Användarens anpassningar (override av defaults)
    cloud_db_url: str = ""
    custom_max_db_gb: float | None = None

    def save(self) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> "StorageTierConfig":
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text())
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception as e:
                _log.warning("Kunde inte läsa storage_tier.json: %s", e)
        return cls()

    def limits(self) -> TierLimits:
        base = TIER_DEFAULTS[self.tier]
        # Applicera eventuella user-overrides
        if self.cloud_db_url:
            base.cloud_db_url = self.cloud_db_url
        if self.custom_max_db_gb is not None:
            base.max_db_gb = self.custom_max_db_gb
        return base


def get_tier() -> StorageTierConfig:
    """Returnera aktiv tier-konfiguration (singleton per process)."""
    return StorageTierConfig.load()


def check_disk_health(db_path: Path | None = None) -> dict:
    """
    Kolla om db-storlek nærmar sig tier-gränsen.
    Returnerar: { tier, current_gb, max_gb, pct, warning }
    """
    import os
    cfg    = get_tier()
    limits = cfg.limits()

    path = db_path or (Path.home() / ".local" / "share" / "nouse" / "field.kuzu")
    current_gb = 0.0
    if path.exists():
        current_gb = os.path.getsize(path) / 1024**3

    warning = limits.warn_if_approaching(current_gb)
    return {
        "tier":       cfg.tier,
        "current_gb": round(current_gb, 2),
        "max_gb":     limits.max_db_gb,
        "pct":        round(current_gb / limits.max_db_gb * 100, 1),
        "warning":    warning,
    }
