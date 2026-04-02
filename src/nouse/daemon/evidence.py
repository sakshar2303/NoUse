"""
b76.daemon.evidence — enkel evidensmodell för autonoma relationer
==================================================================
Ger varje föreslagen relation:
  - evidence_score (0..1)
  - trust_tier (hypotes | indikation | validerad)
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_NUMERIC_CUE_RE = re.compile(r"\b\d+([.,]\d+)?(%|x| gånger| fold)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class EvidenceAssessment:
    score: float
    tier: str
    rationale: str


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _tier(score: float) -> str:
    if score >= 0.8:
        return "validerad"
    if score >= 0.55:
        return "indikation"
    return "hypotes"


def assess_relation(
    relation: dict[str, Any],
    task: dict[str, Any] | None = None,
) -> EvidenceAssessment:
    """
    Heuristik för första versionen av evidensbedömning.
    """
    why = str(relation.get("why") or "").strip()
    src = str(relation.get("src") or "")
    tgt = str(relation.get("tgt") or "")
    rel_type = str(relation.get("type") or relation.get("rel_type") or "")
    domain_src = str(relation.get("domain_src") or "")
    domain_tgt = str(relation.get("domain_tgt") or "")

    score = 0.35
    reasons: list[str] = []

    if why:
        reasons.append("har motivering")
        score += 0.12
        if len(why) >= 80:
            score += 0.1
            reasons.append("motiveringen är detaljrik")
    else:
        score -= 0.12
        reasons.append("saknar motivering")

    if _NUMERIC_CUE_RE.search(why):
        score += 0.12
        reasons.append("innehåller kvantitativa signaler")

    if domain_src and domain_tgt and domain_src != domain_tgt:
        score += 0.08
        reasons.append("domänkorsning med förklaringspotential")

    if rel_type in {"orsakar", "reglerar", "producerar"} and not why:
        score -= 0.08
        reasons.append("stark relationstyp utan evidens")

    if task:
        focus = {str(c).lower() for c in (task.get("concepts") or [])}
        if src.lower() in focus or tgt.lower() in focus:
            score += 0.1
            reasons.append("träffar explicit gap-koncept")

    score = _clamp(score)
    tier = _tier(score)
    rationale = "; ".join(reasons) if reasons else "basbedömning"
    return EvidenceAssessment(score=round(score, 3), tier=tier, rationale=rationale)


def format_why_with_evidence(original_why: str, assessment: EvidenceAssessment) -> str:
    prefix = (
        f"[trust:{assessment.tier} evidence:{assessment.score:.3f}] "
        f"[rationale:{assessment.rationale}]"
    )
    body = (original_why or "").strip()
    if body:
        return f"{prefix} {body}"
    return prefix

