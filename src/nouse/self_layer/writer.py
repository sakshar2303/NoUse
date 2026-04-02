"""
Self-layer writer — Claudes emergenta identitetsmönster
=======================================================
Skriver discoveries och reflektioner till ~/.local/share/nouse/self/
Varje entry är en markdown-fil med frontmatter.
"""
from __future__ import annotations
import asyncio
from datetime import datetime
from pathlib import Path

SELF_DIR = Path.home() / ".local" / "share" / "nouse" / "self"


async def write_discovery(disc: dict) -> None:
    """Skriv en ny nervbana till Self-lagret."""
    SELF_DIR.mkdir(parents=True, exist_ok=True)

    ts    = datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")
    src   = disc["path"][0][0].replace(" ", "_")
    tgt   = disc["path"][-1][2].replace(" ", "_")
    fname = f"{ts}_nervbana_{src}__{tgt}.md"

    path_str = " → ".join(
        f"{s} --[{r}]--> {t}"
        for s, r, t in disc["path"]
    )

    domains = set()
    for s, _, t in disc["path"]:
        pass  # domännamn finns i disc
    domains_str = f"{disc['domain_a']} × {disc['domain_b']}"

    content = f"""---
type: nervbana
timestamp: {datetime.utcnow().isoformat()}
domain_a: {disc['domain_a']}
domain_b: {disc['domain_b']}
hops: {disc['hops']}
novelty: {disc['novelty']:.3f}
---

# Ny nervbana: {domains_str}

**Stig ({disc['hops']} hopp, novelty={disc['novelty']:.1f}):**

{path_str}

**Tolkning:** Systemet hittade en strukturell bro mellan *{disc['domain_a']}*
och *{disc['domain_b']}* via {disc['hops'] - 1} intermediära koncept.
Denna koppling var inte explicit kodad — den uppstod ur grafens topologi.

*Genererad autonomt av b76 brain loop {datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC*
"""
    (SELF_DIR / fname).write_text(content, encoding="utf-8")


async def write_session(growth: list[dict], stats: dict) -> None:
    """Skriv session-reflektion när konversation lade till relationer."""
    SELF_DIR.mkdir(parents=True, exist_ok=True)
    ts    = datetime.utcnow().strftime("%Y-%m-%dT%H%M%S")
    fname = f"{ts}_session_growth.md"

    rels_str = "\n".join(
        f"- {r['src']} --[{r['rel_type']}]--> {r['tgt']}  _{r.get('why','')[:80]}_"
        for r in growth
    )
    content = f"""---
type: session_growth
timestamp: {datetime.utcnow().isoformat()}
new_relations: {len(growth)}
graph_concepts: {stats['concepts']}
graph_relations: {stats['relations']}
---

# Session-tillväxt {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}

Systemet lade autonomt till **{len(growth)} nya relationer** under ett samtal.
Graf: {stats['concepts']} koncept, {stats['relations']} relationer totalt.

## Nya kopplingar

{rels_str}

*Genererat av b76 chat-session {ts}*
"""
    (SELF_DIR / fname).write_text(content, encoding="utf-8")
