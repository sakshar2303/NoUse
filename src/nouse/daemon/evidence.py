"""
nouse.daemon.evidence — Bayesiansk evidensmodell för autonoma relationer
=========================================================================
Ger varje föreslagen relation:
  - evidence_score (0..1)  — kalibrerad Bayesiansk posterior
  - trust_tier             — hypotes | indikation | validerad
  - rationale              — spårbar motiveringskedja

Modell:
  Prior P(true) baseras på strukturella signaler (har motivering, domänkorsning, etc.)
  Likelihood-uppdatering med bekräftande och motstridiiga relationer i grafen:
    P(true | k bekräftningar, m motstridigheter) ∝ prior × LR^k × (1-LR)^m
  LR = likelihood ratio (satt till 3.0 för bekräftning, 0.4 för motbevisning)
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any


_NUMERIC_CUE_RE = re.compile(r"\b\d+([.,]\d+)?(%|x| gånger| fold)?\b", re.IGNORECASE)

# Likelihood ratio för en bekräftande respektive motstridig relation
_LR_CONFIRM     = 3.0   # en bekräftande relation tredubblar oddsen
_LR_CONTRADICT  = 0.4   # en motstridig relation mer än halverar oddsen

# Maximalt bidrag från graph-signaler (förhindrar att grafen ensam driver till 1.0)
_MAX_GRAPH_BOOST = 0.25


@dataclass(frozen=True)
class EvidenceAssessment:
    score: float
    tier: str
    rationale: str


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _tier(score: float) -> str:
    if score >= 0.78:
        return "validerad"
    if score >= 0.52:
        return "indikation"
    return "hypotes"


def _prior_from_signals(
    why: str,
    rel_type: str,
    domain_src: str,
    domain_tgt: str,
    task: dict[str, Any] | None,
    src: str,
    tgt: str,
) -> tuple[float, list[str]]:
    """
    Beräkna prior P(true) från strukturella signaler.
    Returnerar (prior, reasons).
    """
    score = 0.35
    reasons: list[str] = []

    if why:
        reasons.append("har motivering")
        score += 0.12
        if len(why) >= 80:
            score += 0.08
            reasons.append("detaljrik motivering")
        if _NUMERIC_CUE_RE.search(why):
            score += 0.10
            reasons.append("kvantitativ signal")
    else:
        score -= 0.10
        reasons.append("saknar motivering")

    if domain_src and domain_tgt and domain_src != domain_tgt:
        score += 0.07
        reasons.append("domänkorsning")

    if rel_type in {"orsakar", "reglerar", "producerar"} and not why:
        score -= 0.08
        reasons.append("stark relationstyp utan evidens")

    if task:
        focus = {str(c).lower() for c in (task.get("concepts") or [])}
        if src.lower() in focus or tgt.lower() in focus:
            score += 0.08
            reasons.append("träffar explicit gap-koncept")

    return _clamp(score), reasons


def _bayesian_update(
    prior: float,
    confirming: int,
    contradicting: int,
) -> tuple[float, list[str]]:
    """
    Uppdatera prior med Bayesiansk likelihood-ratio.

    Använder log-odds representation för numerisk stabilitet:
      log_odds_posterior = log_odds_prior + k*log(LR_c) + m*log(LR_m)
    """
    if confirming == 0 and contradicting == 0:
        return prior, []

    reasons: list[str] = []
    log_odds_prior = math.log(prior / (1.0 - prior + 1e-9) + 1e-9)

    if confirming > 0:
        log_odds_prior += confirming * math.log(_LR_CONFIRM)
        reasons.append(f"{confirming} bekräftande relation(er) i grafen")

    if contradicting > 0:
        log_odds_prior += contradicting * math.log(_LR_CONTRADICT)
        reasons.append(f"{contradicting} motstridig(a) relation(er) i grafen")

    posterior = 1.0 / (1.0 + math.exp(-log_odds_prior))

    # Begränsa bidraget från graph-signaler
    delta = _clamp(posterior - prior, lo=-_MAX_GRAPH_BOOST, hi=_MAX_GRAPH_BOOST)
    return _clamp(prior + delta), reasons


def assess_relation(
    relation: dict[str, Any],
    task: dict[str, Any] | None = None,
    confirming_relations: int = 0,
    contradicting_relations: int = 0,
) -> EvidenceAssessment:
    """
    Bayesiansk evidensbedömning för en föreslagen relation.

    Args:
        relation:               Relationsdict med src, tgt, type, why, domain_src, domain_tgt.
        task:                   Aktivt research-task (om någon), för gap-matchning.
        confirming_relations:   Antal befintliga grafstigar som stödjer denna relation.
        contradicting_relations: Antal befintliga grafstigar som motstrider denna relation.
    """
    why       = str(relation.get("why") or "").strip()
    src       = str(relation.get("src") or "")
    tgt       = str(relation.get("tgt") or "")
    rel_type  = str(relation.get("type") or relation.get("rel_type") or "")
    domain_src = str(relation.get("domain_src") or "")
    domain_tgt = str(relation.get("domain_tgt") or "")

    prior, prior_reasons = _prior_from_signals(
        why, rel_type, domain_src, domain_tgt, task, src, tgt
    )
    posterior, graph_reasons = _bayesian_update(prior, confirming_relations, contradicting_relations)

    all_reasons = prior_reasons + graph_reasons
    rationale = "; ".join(all_reasons) if all_reasons else "basbedömning"
    tier = _tier(posterior)

    return EvidenceAssessment(
        score=round(posterior, 3),
        tier=tier,
        rationale=rationale,
    )


def format_why_with_evidence(original_why: str, assessment: EvidenceAssessment) -> str:
    prefix = (
        f"[trust:{assessment.tier} evidence:{assessment.score:.3f}] "
        f"[rationale:{assessment.rationale}]"
    )
    body = (original_why or "").strip()
    if body:
        return f"{prefix} {body}"
    return prefix
