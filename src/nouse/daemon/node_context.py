"""
NodeContextEnricher — Berikar noder med källkontext
=====================================================

Steg som körs i NightRun (efter konsolidering):

  1. Hämta noder som saknar kontext (knowledge_audit → missing_context)
  2. Hitta källfiler som nämner noden (grep i IngestPlan-filer)
  3. Extrahera textsnippets runt träffarna
  4. Anropa LLM för att skriva summary + claims (respekterar tier-gräns)
  5. Spara via upsert_concept_knowledge

Tier-styrning:
  small:  0 tecken kontext → hoppar över LLM, kör bara graph-backfill
  medium: 2 000 tecken per nod → LLM-summary + snippet
  large:  10 000 tecken per nod → LLM-summary + djup analys

Denna modul är *asynkron* och körs som del av NightRun.
Den kan också triggas manuellt: b76 enrich-nodes
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nouse.field.surface import FieldSurface

_log = logging.getLogger("nouse.node_context")

# Antal tecken runt varje grep-träff att inkludera som snippet
_SNIPPET_WINDOW = 300

# Max antal källfiler att söka per nod
_MAX_SOURCE_FILES = 20

# Max antal snippets att skicka till LLM per nod
_MAX_SNIPPETS = 6


@dataclass
class EnrichResult:
    enriched:   int = 0
    skipped:    int = 0
    failed:     int = 0
    duration:   float = 0.0


# ── Källfilssökning ───────────────────────────────────────────────────────────

def _find_source_files() -> list[Path]:
    """Hämta godkända källfiler från IngestPlan (om den finns)."""
    try:
        from nouse.daemon.disk_mapper import IngestPlan
        plan = IngestPlan.load()
        if plan:
            files: list[Path] = []
            for p in plan.approved_paths:
                path = Path(p)
                if path.is_file():
                    files.append(path)
                elif path.is_dir():
                    # Expandera kataloger — ta textfiler
                    for f in path.rglob("*"):
                        if f.is_file() and f.suffix.lower() in {
                            ".md", ".txt", ".pdf", ".py", ".rs", ".ts",
                            ".org", ".tex", ".rst", ".ipynb",
                        }:
                            files.append(f)
            return files[:_MAX_SOURCE_FILES * 10]
    except Exception:
        pass
    return []


def _extract_snippets(node_name: str, files: list[Path], max_chars: int) -> list[str]:
    """
    Sök efter node_name i källfiler, returnera textsnippets.
    Stannar när total text >= max_chars.
    """
    pattern = re.compile(re.escape(node_name.replace("_", " ")), re.IGNORECASE)
    alt_pattern = re.compile(re.escape(node_name), re.IGNORECASE)

    snippets: list[str] = []
    total_chars = 0

    for fpath in files[:_MAX_SOURCE_FILES]:
        if total_chars >= max_chars:
            break
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for m in list(pattern.finditer(text)) + list(alt_pattern.finditer(text)):
            start = max(0, m.start() - _SNIPPET_WINDOW)
            end   = min(len(text), m.end() + _SNIPPET_WINDOW)
            snippet = text[start:end].strip()
            if snippet and snippet not in snippets:
                snippets.append(snippet)
                total_chars += len(snippet)
                if len(snippets) >= _MAX_SNIPPETS or total_chars >= max_chars:
                    break

        if total_chars >= max_chars:
            break

    return snippets


# ── LLM-berikning ─────────────────────────────────────────────────────────────

async def _enrich_node_with_llm(
    node_name: str,
    domain: str,
    snippets: list[str],
    max_context_chars: int,
    *,
    llm_client,
) -> tuple[str, list[str]] | None:
    """
    Anropa LLM med snippets, returnera (summary, claims).
    Returnerar None om LLM-anropet misslyckas.
    """
    context_text = "\n\n---\n\n".join(snippets)
    if len(context_text) > max_context_chars:
        context_text = context_text[:max_context_chars] + "…"

    prompt = (
        f"Du är ett kunskapssystem. Analysera texten nedan om konceptet '{node_name}' "
        f"(domän: {domain}) och svara EXAKT i detta JSON-format:\n\n"
        '{"summary": "En mening som förklarar vad detta är.", '
        '"claims": ["Påstående 1.", "Påstående 2.", "Påstående 3."]}\n\n'
        f"Källtext:\n{context_text}\n\n"
        "Svara bara med JSON, inget annat."
    )

    try:
        resp = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            workload="extract",
            max_tokens=300,
        )
        raw = (resp or "").strip()

        # Extrahera JSON ur eventuellt markdown-block
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        import json
        data = json.loads(raw)
        summary = str(data.get("summary", "")).strip()
        claims  = [str(c).strip() for c in data.get("claims", []) if str(c).strip()]
        if summary:
            return summary, claims
    except Exception as e:
        _log.debug("LLM-berikning av '%s' misslyckades: %s", node_name, e)

    return None


# ── Huvudfunktion ──────────────────────────────────────────────────────────────

async def enrich_nodes(
    field: "FieldSurface",
    *,
    max_nodes: int = 50,
    max_minutes: float = 20.0,
    dry_run: bool = False,
) -> EnrichResult:
    """
    Berikar noder som saknar kontext med LLM-genererad summary+claims.
    Respekterar aktiv StorageTier.
    """
    from nouse.daemon.storage_tier import get_tier

    tier   = get_tier()
    limits = tier.limits()

    # Small: inga kontext-bytes → hoppa över LLM, kör bara graph-backfill
    if limits.context_per_node_chars == 0:
        _log.info("NodeContextEnricher: tier=small → kör enbart graph-backfill")
        return await _graph_only_backfill(field, max_nodes=max_nodes)

    max_chars = limits.context_per_node_chars

    # Hämta noder som saknar kontext
    try:
        audit = field.knowledge_audit(limit=max_nodes * 2, strict=False)
    except Exception as e:
        _log.warning("knowledge_audit misslyckades: %s", e)
        return EnrichResult()

    missing = [
        n for n in audit.get("nodes", [])
        if not n.get("has_context")
    ][:max_nodes]

    if not missing:
        _log.info("NodeContextEnricher: alla %d noder har redan kontext", audit.get("total", 0))
        return EnrichResult()

    _log.info(
        "NodeContextEnricher: %d noder saknar kontext (tier=%s, max=%d tecken/nod)",
        len(missing), tier.tier, max_chars,
    )

    source_files = _find_source_files()
    if not source_files:
        _log.info("Inga källfiler i IngestPlan — faller tillbaka till graph-backfill")
        return await _graph_only_backfill(field, max_nodes=max_nodes)

    # LLM-klient (återanvänder b76:s interna klient)
    try:
        from nouse.ollama_client.client import get_client
        llm_client = get_client()
    except Exception as e:
        _log.warning("Kunde inte skapa LLM-klient: %s — kör graph-backfill", e)
        return await _graph_only_backfill(field, max_nodes=max_nodes)

    result  = EnrichResult()
    t0      = time.monotonic()
    deadline = t0 + max_minutes * 60

    for node_info in missing:
        if time.monotonic() > deadline:
            _log.warning("NodeContextEnricher: tidsgräns nådd")
            break

        name   = node_info.get("name", "")
        domain = node_info.get("domain", "okänd")
        if not name:
            continue

        snippets = _extract_snippets(name, source_files, max_chars)

        if not snippets:
            # Ingen källtext hittad — graph-backfill för denna nod
            if not dry_run:
                try:
                    field.backfill_concept_knowledge(name)
                except Exception:
                    pass
            result.skipped += 1
            await asyncio.sleep(0)
            continue

        enriched = await _enrich_node_with_llm(
            name, domain, snippets, max_chars, llm_client=llm_client
        )

        if enriched and not dry_run:
            summary, claims = enriched
            try:
                field.upsert_concept_knowledge(
                    name,
                    summary=summary,
                    claims=claims,
                    evidence_refs=[f"source_snippet:{s[:80]}" for s in snippets[:2]],
                    related_terms=[domain],
                    uncertainty=0.35,
                )
                result.enriched += 1
                _log.debug("Berikat: %s — summary=%d tecken, claims=%d", name, len(summary), len(claims))
            except Exception as e:
                _log.warning("Kunde inte spara kontext för '%s': %s", name, e)
                result.failed += 1
        elif enriched:
            result.enriched += 1  # dry_run räknar ändå
        else:
            # LLM misslyckades — graph-backfill som fallback
            if not dry_run:
                try:
                    field.backfill_concept_knowledge(name)
                except Exception:
                    pass
            result.failed += 1

        await asyncio.sleep(0)

    result.duration = round(time.monotonic() - t0, 2)
    _log.info(
        "NodeContextEnricher klar: berikat=%d hoppade=%d misslyckade=%d (%.1fs)",
        result.enriched, result.skipped, result.failed, result.duration,
    )
    return result


async def _graph_only_backfill(field: "FieldSurface", *, max_nodes: int) -> EnrichResult:
    """Kör befintlig graph-baserad backfill (utan LLM) för noder som saknar kontext."""
    try:
        audit   = field.knowledge_audit(limit=max_nodes * 2, strict=False)
        missing = [n for n in audit.get("nodes", []) if not n.get("has_context")][:max_nodes]
        for node in missing:
            name = node.get("name", "")
            if name:
                try:
                    field.backfill_concept_knowledge(name)
                except Exception:
                    pass
            await asyncio.sleep(0)
        return EnrichResult(enriched=len(missing))
    except Exception as e:
        _log.warning("graph_only_backfill misslyckades: %s", e)
        return EnrichResult()
