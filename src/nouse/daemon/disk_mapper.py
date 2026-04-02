"""
DiskMapper — Fas 1+2 i Nouse onboarding
=========================================

Fas 1 (sekunder): Skannar filsystemet utan LLM.
  - Räknar filer per typ och katalog
  - Skattar semantisk densitet (filstorlek × relevanspoäng)
  - Identifierar brus-kataloger att skippa

Fas 2 (interaktiv): Presenterar fynd för användaren.
  - Visar förslag grupperat per domän/filtyp
  - Användaren skapar/godkänner/avvisar ingest-plan
  - Sparar plan → daemon hämtar den

Flöde:
    mapper = DiskMapper(["/home/bjorn", "/media/bjorn/iic"])
    report = mapper.scan()            # Fas 1: snabb
    plan   = mapper.plan(report)      # Fas 2: rankat förslag
    plan.present()                    # Visa för användaren
    plan.save()                       # Daemon hämtar härifrån
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator

# ── Konfiguration ─────────────────────────────────────────────────────────────

PLAN_FILE = Path.home() / ".local" / "share" / "b76" / "ingest_plan.json"

# Filtyper och deras semantiska relevansvikt (0–1)
FILE_RELEVANCE: dict[str, float] = {
    ".md":   1.0,
    ".txt":  0.9,
    ".pdf":  0.95,
    ".py":   0.8,
    ".rs":   0.75,
    ".ts":   0.7,
    ".js":   0.5,
    ".json": 0.4,
    ".yaml": 0.5,
    ".yml":  0.5,
    ".csv":  0.6,
    ".html": 0.3,
    ".ipynb":0.85,
    ".org":  0.9,
    ".tex":  0.95,
    ".rst":  0.85,
}

# Kataloger att alltid hoppa över
ALWAYS_SKIP = frozenset({
    ".git", ".hg", ".svn", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "venv",
    ".cache", "cache", "tmp", "temp", "dist", "build",
    ".next", ".nuxt", ".idea", ".vscode", "Trash", ".Trash",
    "snap", "flatpak", ".docker", ".nvidia", ".local/share/Steam",
    "proc", "sys", "dev",
})

# Kataloger som troligtvis är brus (föreslås skippa till användaren)
LIKELY_NOISE_PATTERNS = {
    r"downloads?$":         "Nedladdningar (ofta temporärt)",
    r"\.npm$":              "NPM-cache",
    r"\.cargo/registry":    "Rust-paketcache",
    r"site-packages":       "Python-paketinstallationer",
    r"Library/Caches":      "macOS-cache",
    r"AppData/Local/Temp":  "Windows-temp",
}

# Max filstorlek att ta med (> detta = troligtvis binär/data)
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

# Optimal filstorlek för extraktion (sweet spot)
OPTIMAL_MIN = 500     # bytes
OPTIMAL_MAX = 50_000  # bytes


# ── Datamodeller ──────────────────────────────────────────────────────────────

@dataclass
class FileScore:
    path: str
    size: int
    ext: str
    mtime: float
    relevance: float      # filtyp-vikt
    recency: float        # 0–1, nyare = högre
    size_score: float     # 0–1, sweet spot = 1
    final_score: float    # vägt snitt
    domain_hint: str      # gissad domän från sökväg


@dataclass
class DirProfile:
    path: str
    file_count: int
    total_size: int
    avg_relevance: float
    noise_reason: str | None     # None = ej brus


@dataclass
class ScanReport:
    roots: list[str]
    total_files: int
    total_size_bytes: int
    by_extension: dict[str, int]     # ext → antal filer
    dir_profiles: list[DirProfile]
    top_files: list[FileScore]       # top 500 rankade filer
    noise_dirs: list[str]            # föreslagna att skippa
    scan_seconds: float


@dataclass
class IngestPlan:
    approved_paths: list[str]        # filer/kataloger att ingest:a
    skipped_dirs: list[str]
    estimated_files: int
    estimated_llm_calls: int
    notes: list[str]

    def save(self) -> Path:
        PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
        PLAN_FILE.write_text(json.dumps(asdict(self), indent=2))
        return PLAN_FILE

    @classmethod
    def load(cls) -> "IngestPlan | None":
        if not PLAN_FILE.exists():
            return None
        d = json.loads(PLAN_FILE.read_text())
        return cls(**d)


# ── Hjälpfunktioner ───────────────────────────────────────────────────────────

def _recency_score(mtime: float, now: float) -> float:
    """Nyare filer rankas högre. 30 dagar gammal = 0.5."""
    age_days = (now - mtime) / 86400
    return math.exp(-age_days / 30)


def _size_score(size: int) -> float:
    """Sweet spot: 500B–50KB = 1.0. Extrema storlekar ger lägre poäng."""
    if size < OPTIMAL_MIN:
        return size / OPTIMAL_MIN
    if size > OPTIMAL_MAX:
        return OPTIMAL_MAX / size
    return 1.0


def _domain_hint(path: Path) -> str:
    """Gissa domän från katalognamn/filnamn."""
    parts = [p.lower() for p in path.parts]
    keywords = {
        "ocean": "oceanografi", "marine": "oceanografi", "sea": "oceanografi",
        "neuro": "neurovetenskap", "brain": "neurovetenskap", "neural": "neurovetenskap",
        "ai": "AI/ML", "ml": "AI/ML", "deep": "AI/ML", "model": "AI/ML",
        "physics": "fysik", "quantum": "fysik",
        "code": "kod", "src": "kod", "projects": "kod",
        "research": "forskning", "paper": "forskning", "arxiv": "forskning",
        "notes": "anteckningar", "journal": "anteckningar", "diary": "anteckningar",
        "work": "arbete", "docs": "dokumentation",
    }
    for part in parts:
        for kw, domain in keywords.items():
            if kw in part:
                return domain
    return "okänd"


def _is_noise_dir(path: Path) -> str | None:
    """Returnera brus-orsak om katalogen troligtvis är brus, annars None."""
    path_str = str(path).lower()
    for pattern, reason in LIKELY_NOISE_PATTERNS.items():
        if re.search(pattern, path_str, re.IGNORECASE):
            return reason
    return None


def _should_skip_dir(name: str) -> bool:
    return name.lower() in ALWAYS_SKIP or name.startswith(".")


# ── Fas 1: Skanner ────────────────────────────────────────────────────────────

class DiskMapper:
    def __init__(self, roots: list[str | Path]):
        self.roots = [Path(r) for r in roots]

    def _walk(self, allowed_exts: set[str] | None = None) -> Iterator[Path]:
        for root in self.roots:
            if not root.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if not _should_skip_dir(d)
                ]
                for fname in filenames:
                    p = Path(dirpath) / fname
                    if allowed_exts and p.suffix.lower() not in allowed_exts:
                        continue
                    yield p

    def scan(self, max_files: int | None = None) -> ScanReport:
        """Fas 1: Snabb filsystemsscanning utan LLM."""
        from nouse.daemon.storage_tier import get_tier
        tier = get_tier()
        limits = tier.limits()

        # Respektera tier-gränser (men tillåt explicit override)
        effective_max = max_files if max_files is not None else limits.max_scan_files

        # Tier large = alla kända filtyper; annars filter
        allowed_exts: set[str] | None = None
        if limits.scan_extensions:  # tom lista = inga restriktioner
            allowed_exts = {e.lower() for e in limits.scan_extensions}

        t0 = time.monotonic()
        now = time.time()

        by_ext: dict[str, int] = {}
        dir_file_counts: dict[str, int] = {}
        dir_sizes: dict[str, int] = {}
        dir_relevances: dict[str, list[float]] = {}
        noise_dirs: set[str] = set()
        scored: list[FileScore] = []
        total_size = 0
        total_files = 0

        for path in self._walk(allowed_exts=allowed_exts):
            if total_files >= effective_max:
                break

            ext = path.suffix.lower()
            if ext not in FILE_RELEVANCE:
                continue

            try:
                stat = path.stat()
            except (PermissionError, OSError):
                continue

            size = stat.st_size
            if size > MAX_FILE_SIZE or size == 0:
                continue

            total_files += 1
            total_size += size
            by_ext[ext] = by_ext.get(ext, 0) + 1

            parent = str(path.parent)
            dir_file_counts[parent] = dir_file_counts.get(parent, 0) + 1
            dir_sizes[parent] = dir_sizes.get(parent, 0) + size
            if parent not in dir_relevances:
                dir_relevances[parent] = []

            rel   = FILE_RELEVANCE[ext]
            rec   = _recency_score(stat.st_mtime, now)
            sizsc = _size_score(size)
            final = 0.4 * rel + 0.35 * rec + 0.25 * sizsc

            dir_relevances[parent].append(rel)

            scored.append(FileScore(
                path=str(path),
                size=size,
                ext=ext,
                mtime=stat.st_mtime,
                relevance=rel,
                recency=rec,
                size_score=sizsc,
                final_score=final,
                domain_hint=_domain_hint(path),
            ))

            noise = _is_noise_dir(path.parent)
            if noise:
                noise_dirs.add(parent)

        # Sortera top-500
        scored.sort(key=lambda f: f.final_score, reverse=True)
        top = scored[:500]

        # Bygg katalog-profiler
        dir_profiles = []
        for dpath, count in dir_file_counts.items():
            noise_reason = _is_noise_dir(Path(dpath))
            avg_rel = (
                sum(dir_relevances[dpath]) / len(dir_relevances[dpath])
                if dir_relevances.get(dpath) else 0.0
            )
            dir_profiles.append(DirProfile(
                path=dpath,
                file_count=count,
                total_size=dir_sizes.get(dpath, 0),
                avg_relevance=round(avg_rel, 3),
                noise_reason=noise_reason,
            ))

        dir_profiles.sort(key=lambda d: d.file_count, reverse=True)

        return ScanReport(
            roots=[str(r) for r in self.roots],
            total_files=total_files,
            total_size_bytes=total_size,
            by_extension=dict(sorted(by_ext.items(), key=lambda x: x[1], reverse=True)),
            dir_profiles=dir_profiles[:100],
            top_files=top,
            noise_dirs=sorted(noise_dirs),
            scan_seconds=round(time.monotonic() - t0, 2),
        )

    # ── Fas 2: Plan ───────────────────────────────────────────────────────────

    def plan(
        self,
        report: ScanReport,
        *,
        max_files: int = 2000,
        score_threshold: float = 0.55,
        skip_dirs: list[str] | None = None,
    ) -> IngestPlan:
        """
        Fas 2: Skapa ett rankat ingest-förslag.

        max_files:        max antal filer att ta med
        score_threshold:  minimumpoäng för att ta med en fil
        skip_dirs:        kataloger användaren explicit vill skippa
        """
        skip_set = set(skip_dirs or []) | set(report.noise_dirs)

        approved: list[str] = []
        for fs in report.top_files:
            if len(approved) >= max_files:
                break
            if fs.final_score < score_threshold:
                break
            # Skippa om filen ligger i en skippat katalog
            if any(str(fs.path).startswith(d) for d in skip_set):
                continue
            approved.append(fs.path)

        # LLM-uppskattning: 1 anrop per ~2200 tecken, snitt 800 tecken/fil
        avg_chars = 800
        est_llm = max(1, len(approved) * avg_chars // 2200)

        notes = [
            f"{report.total_files} filer hittades på {report.scan_seconds}s",
            f"{len(report.noise_dirs)} brus-kataloger identifierade och hoppades över",
            f"Av dessa är {len(approved)} filer ≥ {score_threshold} relevanspoäng",
            f"Uppskattade LLM-anrop: ~{est_llm} (kan ta ~{est_llm//10 or 1} min)",
        ]

        return IngestPlan(
            approved_paths=approved,
            skipped_dirs=sorted(skip_set),
            estimated_files=len(approved),
            estimated_llm_calls=est_llm,
            notes=notes,
        )

    def present(self, report: ScanReport, plan: IngestPlan) -> None:
        """Skriv ut en läsbar sammanfattning för användaren."""
        print("\n" + "═" * 60)
        print("  🗺️  NOUSE DISKKARTLÄGGNING")
        print("═" * 60)

        print(f"\n📁 Skannade: {', '.join(report.roots)}")
        print(f"   {report.total_files:,} relevanta filer hittades på {report.scan_seconds}s")
        print(f"   Total storlek: {report.total_size_bytes / 1e9:.1f} GB")

        print("\n📊 Filtyper:")
        for ext, count in list(report.by_extension.items())[:8]:
            bar = "█" * min(30, count // max(1, report.total_files // 30))
            print(f"   {ext:8s} {count:6,}  {bar}")

        if report.noise_dirs:
            print(f"\n🔇 Föreslår att hoppa över ({len(report.noise_dirs)} brus-kataloger):")
            for d in report.noise_dirs[:5]:
                reason = _is_noise_dir(Path(d)) or ""
                print(f"   ⊘  {d}  ({reason})")
            if len(report.noise_dirs) > 5:
                print(f"   ... och {len(report.noise_dirs)-5} till")

        print(f"\n🎯 Ingest-plan: {plan.estimated_files:,} filer")
        print(f"   Uppskattade LLM-anrop: ~{plan.estimated_llm_calls:,}")
        print(f"   Uppskattad tid: ~{plan.estimated_llm_calls//10 or 1} minuter")

        print("\n🏆 Topp 10 filer (högst relevanspoäng):")
        for fs in plan.approved_paths[:10]:
            f = next((x for x in report.top_files if x.path == fs), None)
            if f:
                print(f"   {f.final_score:.2f}  {f.domain_hint:15s}  {Path(f.path).name}")

        print("\n💡 Råd:")
        for note in plan.notes:
            print(f"   • {note}")
        print()
