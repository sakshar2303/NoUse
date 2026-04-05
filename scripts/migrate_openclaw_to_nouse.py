#!/usr/bin/env python3
"""
migrate_openclaw_to_nouse.py

Reads all openclaw memory/workspace .md files and ingests them
into the Nouse knowledge graph via brain.learn().

Run once. Safe to re-run (duplicate relations are ignored).
"""
import sys
import time
from pathlib import Path

SOURCES = [
    Path.home() / ".openclaw/workspace/memory",
    Path.home() / ".openclaw/agents/heavy/workspace/memory",
    Path.home() / ".openclaw/agents/main/workspace/memory",
    Path.home() / ".openclaw/agents/researcher/workspace/memory",
    Path.home() / ".openclaw/agents/heavy/workspace",
]

SKIP_PATTERNS = [
    "sessions.json", "openclaw.json", "auth-profiles", "models.json",
    "node_modules", ".git", "extensions", "plugin.json",
]

MAX_CHARS = 6000  # chunk size to avoid overwhelming extractor


def should_skip(path: Path) -> bool:
    return any(p in str(path) for p in SKIP_PATTERNS)


def chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i:i + size]


def main():
    import nouse
    brain = nouse.attach()

    files = []
    for source in SOURCES:
        if source.exists():
            files += [p for p in source.rglob("*.md") if not should_skip(p)]

    files = sorted(set(files))
    print(f"Found {len(files)} files to ingest\n")

    ok = 0
    failed = 0

    for i, path in enumerate(files, 1):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if not text or len(text) < 50:
                print(f"  [{i}/{len(files)}] SKIP (too short): {path.name}")
                continue

            tag = f"openclaw/{path.parent.name}/{path.stem}"
            print(f"  [{i}/{len(files)}] Ingesting: {path.name} ({len(text)} chars)")

            for chunk in chunks(text, MAX_CHARS):
                brain.learn(
                    prompt=f"[Knowledge from openclaw memory: {path.name}]",
                    response=chunk,
                    source=tag,
                )
                time.sleep(0.3)  # don't hammer the extractor

            ok += 1

        except Exception as e:
            print(f"  [{i}/{len(files)}] ERROR: {path.name} — {e}")
            failed += 1

    print(f"\n✅ Done. Ingested: {ok}  Failed: {failed}")

    stats = brain.stats()
    print(f"Graph now: {stats}")


if __name__ == "__main__":
    main()
