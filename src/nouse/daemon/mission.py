"""
b76.daemon.mission — mission-lager för autonom riktning + mätbar progression
===========================================================================
Håller ett globalt mål ("mission") som kan seeda research-queue och logga
kontinuerliga metrics per brain-loop-cykel.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

MISSION_PATH = Path.home() / ".local" / "share" / "b76" / "mission.json"
MISSION_METRICS_PATH = Path.home() / ".local" / "share" / "b76" / "mission_metrics.jsonl"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_list(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = str(value or "").strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def load_mission(path: Path = MISSION_PATH) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    mission = str(data.get("mission") or "").strip()
    if not mission:
        return None
    data["mission"] = mission
    data["focus_domains"] = _clean_list(data.get("focus_domains") or [])
    data["kpis"] = _clean_list(data.get("kpis") or [])
    data["constraints"] = _clean_list(data.get("constraints") or [])
    return data


def save_mission(
    mission: str,
    *,
    north_star: str = "",
    focus_domains: Iterable[str] | None = None,
    kpis: Iterable[str] | None = None,
    constraints: Iterable[str] | None = None,
    path: Path = MISSION_PATH,
) -> dict[str, Any]:
    existing = load_mission(path) or {}
    now = _utcnow()
    payload: dict[str, Any] = {
        "mission": str(mission).strip(),
        "north_star": str(north_star).strip(),
        "focus_domains": _clean_list(focus_domains),
        "kpis": _clean_list(kpis),
        "constraints": _clean_list(constraints),
        "updated_at": now,
        "created_at": existing.get("created_at") or now,
        "version": int(existing.get("version", 0) or 0) + 1,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def clear_mission(path: Path = MISSION_PATH) -> bool:
    if not path.exists():
        return False
    path.unlink()
    return True


def mission_summary(mission: dict[str, Any] | None) -> str:
    if not mission:
        return "ingen aktiv mission"
    base = str(mission.get("mission") or "").strip()
    if not base:
        return "ingen aktiv mission"
    domains = mission.get("focus_domains") or []
    if not domains:
        return base
    return f"{base} [fokus: {', '.join(domains[:5])}]"


def build_seed_tasks(
    field: Any,
    mission: dict[str, Any] | None,
    *,
    max_new: int = 2,
) -> list[dict[str, Any]]:
    if not mission or max_new <= 0:
        return []

    mission_text = str(mission.get("mission") or "").strip()
    if not mission_text:
        return []
    north_star = str(mission.get("north_star") or mission_text).strip()
    focus_domains = _clean_list(mission.get("focus_domains") or [])
    if not focus_domains:
        return []

    try:
        existing_domains = [str(d) for d in field.domains()]
    except Exception:
        existing_domains = []

    by_lower = {d.lower(): d for d in existing_domains}
    tasks: list[dict[str, Any]] = []
    seen_query: set[str] = set()

    def _append(task: dict[str, Any]) -> None:
        qkey = str(task.get("query", "")).strip().lower()
        if not qkey or qkey in seen_query:
            return
        seen_query.add(qkey)
        tasks.append(task)

    for raw_domain in focus_domains:
        if len(tasks) >= max_new:
            break
        norm = raw_domain.lower()
        resolved_domain = by_lower.get(norm, raw_domain)
        exists = norm in by_lower

        concepts: list[str] = []
        if exists:
            try:
                concepts = [
                    str(c.get("name"))
                    for c in field.concepts(domain=resolved_domain)
                    if str(c.get("name") or "").strip()
                ][:4]
            except Exception:
                concepts = []

        if exists:
            query = (
                f"Mission '{north_star}': hitta verifierbara mekanismer i domänen "
                f"'{resolved_domain}' och föreslå relationer med tydlig evidens och antaganden."
            )
            rationale = (
                "Mission-fokusdomän behöver fördjupning med hög evidens för att driva "
                "långsiktig autonom utveckling."
            )
            gap_type = "mission_focus_domain"
            priority = 0.98
        else:
            query = (
                f"Mission '{north_star}': bygg en första kunskapskarta för domänen "
                f"'{resolved_domain}' med nyckelkoncept, mekanismer och testbara relationer."
            )
            rationale = (
                "Mission-fokusdomän saknas i grafen och behöver bootstrap-kunskap innan "
                "djupare autonom forskning kan ske."
            )
            gap_type = "mission_bootstrap_domain"
            priority = 0.995

        _append(
            {
                "domain": resolved_domain,
                "concepts": concepts,
                "query": query,
                "rationale": rationale,
                "priority": priority,
                "gap_type": gap_type,
                "source": "mission_engine_v1",
            }
        )

    for a, b in combinations(focus_domains, 2):
        if len(tasks) >= max_new:
            break
        resolved_a = by_lower.get(a.lower(), a)
        resolved_b = by_lower.get(b.lower(), b)
        _append(
            {
                "domain": f"{resolved_a} × {resolved_b}",
                "concepts": [resolved_a, resolved_b],
                "query": (
                    f"Mission '{north_star}': kartlägg tvärdomän-bryggor mellan "
                    f"'{resolved_a}' och '{resolved_b}' med explicita evidensnivåer."
                ),
                "rationale": (
                    "Mission kräver tvärdomänintegration snarare än isolerade kunskapsöar."
                ),
                "priority": 0.96,
                "gap_type": "mission_cross_domain",
                "source": "mission_engine_v1",
            }
        )

    return tasks[:max_new]


def append_cycle_metric(
    *,
    mission: dict[str, Any] | None,
    cycle: int,
    graph_stats: dict[str, Any],
    queue: dict[str, Any],
    limbic: dict[str, float],
    new_relations: int,
    discoveries: int,
    bisoc_candidates: int,
    knowledge_coverage: dict[str, float] | None = None,
    path: Path = MISSION_METRICS_PATH,
) -> dict[str, Any] | None:
    if not mission:
        return None

    row = {
        "ts": _utcnow(),
        "cycle": int(cycle),
        "mission": str(mission.get("mission") or ""),
        "mission_version": int(mission.get("version", 0) or 0),
        "north_star": str(mission.get("north_star") or ""),
        "focus_domains": list(mission.get("focus_domains") or []),
        "graph": {
            "concepts": int(graph_stats.get("concepts", 0) or 0),
            "relations": int(graph_stats.get("relations", 0) or 0),
        },
        "delta": {
            "new_relations": int(new_relations),
            "discoveries": int(discoveries),
            "bisoc_candidates": int(bisoc_candidates),
        },
        "queue": {
            "pending": int(queue.get("pending", 0) or 0),
            "in_progress": int(queue.get("in_progress", 0) or 0),
            "done": int(queue.get("done", 0) or 0),
            "failed": int(queue.get("failed", 0) or 0),
        },
        "limbic": {
            "lambda": float(limbic.get("lambda", 0.0) or 0.0),
            "arousal": float(limbic.get("arousal", 0.0) or 0.0),
            "dopamine": float(limbic.get("dopamine", 0.0) or 0.0),
            "noradrenaline": float(limbic.get("noradrenaline", 0.0) or 0.0),
        },
    }
    if knowledge_coverage:
        row["knowledge_coverage"] = {
            "context": float(knowledge_coverage.get("context", 0.0) or 0.0),
            "facts": float(knowledge_coverage.get("facts", 0.0) or 0.0),
            "strong_facts": float(knowledge_coverage.get("strong_facts", 0.0) or 0.0),
            "complete": float(knowledge_coverage.get("complete", 0.0) or 0.0),
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_recent_metrics(limit: int = 20, path: Path = MISSION_METRICS_PATH) -> list[dict[str, Any]]:
    if limit <= 0 or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        item = line.strip()
        if not item:
            continue
        try:
            parsed = json.loads(item)
        except Exception:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows[-limit:]
