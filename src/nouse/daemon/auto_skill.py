from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any, Literal

from nouse.daemon.evidence import assess_relation

AutoSkillMode = Literal["disabled", "observe", "shadow", "sandbox", "production"]
ClaimRoute = Literal["prod", "sandbox", "drop"]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _parse_mode(raw: str) -> AutoSkillMode:
    mode = str(raw or "disabled").strip().lower()
    if mode in {"disabled", "observe", "shadow", "sandbox", "production"}:
        return mode  # type: ignore[return-value]
    return "disabled"


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def relation_fingerprint(relation: dict[str, Any]) -> str:
    payload = "|".join(
        [
            _normalize_token(relation.get("src")),
            _normalize_token(relation.get("type") or relation.get("rel_type")),
            _normalize_token(relation.get("tgt")),
            _normalize_token(relation.get("domain_src")),
            _normalize_token(relation.get("domain_tgt")),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


@dataclass(frozen=True)
class AutoSkillPolicy:
    mode: AutoSkillMode
    prod_threshold: float
    sandbox_threshold: float
    enforce_writes: bool

    @classmethod
    def from_env(cls) -> "AutoSkillPolicy":
        return cls(
            mode=_parse_mode(os.getenv("NOUSE_AUTO_SKILL_MODE", "observe")),
            prod_threshold=float(os.getenv("NOUSE_AUTO_SKILL_CONFIDENCE_THRESHOLD_PROD", "0.75")),
            sandbox_threshold=float(os.getenv("NOUSE_AUTO_SKILL_CONFIDENCE_THRESHOLD_SANDBOX", "0.55")),
            enforce_writes=str(os.getenv("NOUSE_AUTO_SKILL_ENFORCE_WRITES", "0")).strip().lower()
            in {"1", "true", "yes", "on"},
        )


@dataclass(frozen=True)
class ClaimDecision:
    fingerprint: str
    heuristic_score: float
    auto_score: float
    tier: str
    route: ClaimRoute
    reasons: list[str]


def evaluate_claim(
    relation: dict[str, Any],
    *,
    policy: AutoSkillPolicy,
    seen_fingerprints: set[str] | None = None,
    task: dict[str, Any] | None = None,
) -> ClaimDecision:
    ass = assess_relation(relation, task=task)
    score = float(ass.score)
    reasons: list[str] = [ass.rationale]
    fp = relation_fingerprint(relation)

    if seen_fingerprints is not None:
        if fp in seen_fingerprints:
            score -= 0.2
            reasons.append("duplikat i samma batch")
        else:
            seen_fingerprints.add(fp)

    if _normalize_token(relation.get("src")) == _normalize_token(relation.get("tgt")):
        score -= 0.15
        reasons.append("sjalvrefererande relation")

    score = round(_clamp(score), 3)
    if score >= policy.prod_threshold:
        route: ClaimRoute = "prod"
    elif score >= policy.sandbox_threshold:
        route = "sandbox"
    else:
        route = "drop"

    if score >= 0.8:
        tier = "validerad"
    elif score >= 0.55:
        tier = "indikation"
    else:
        tier = "hypotes"

    if policy.mode in {"disabled", "observe", "shadow"}:
        route = "prod"

    return ClaimDecision(
        fingerprint=fp,
        heuristic_score=float(ass.score),
        auto_score=score,
        tier=tier,
        route=route,
        reasons=reasons,
    )
