from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from nouse.daemon.research_queue import enqueue_gap_tasks, queue_stats
from nouse.daemon.system_events import enqueue_system_event, request_wake
from nouse.field.surface import FieldSurface

_DEFAULT_MISSION = (
    "Kickstarta b76 till en snabb personlig assistent med autonom bakgrundsexekvering "
    "och verifierbar kunskapstillvaxt."
)
_DEFAULT_REPO_ROOT = "/home/bjorn/projects/GH_autonom_b76"
_DEFAULT_IIC1_ROOT = "/home/bjorn/projects"

_AGENT_TEMPLATES: list[dict[str, str]] = [
    {
        "name": "scope_mapper",
        "focus": "kartlagg arkitektur, flaskhalsar och risker i kodbasen",
        "deliverable": "prioriterad arkitekturkarta med topp-5 risker",
    },
    {
        "name": "delivery_planner",
        "focus": "bryt ner mal till korta, verifierbara leveranser",
        "deliverable": "30-dagars leveransplan med tydliga milstolpar",
    },
    {
        "name": "quality_guard",
        "focus": "identifiera testluckor, driftluckor och observability-gap",
        "deliverable": "test- och driftbacklog med hojd forslagstakt",
    },
    {
        "name": "memory_trainer",
        "focus": "forbattra minneskvalitet, deduplicering och retrieval precision",
        "deliverable": "forslag pa minnespolicy och valideringsmatriser",
    },
    {
        "name": "automation_builder",
        "focus": "automatisera upprepade operatorfloden i daemon/cli/web",
        "deliverable": "lista pa automationskandidater med ROI-estimat",
    },
    {
        "name": "evidence_researcher",
        "focus": "hamta extern evidens for antaganden i mission och design",
        "deliverable": "kort evidensrapport med kallsammanfattning",
    },
]


def _project_root() -> Path:
    # .../src/b76/daemon/kickstart.py -> project root is parents[3]
    return Path(__file__).resolve().parents[3]


def _normalize_repo_root(raw: str) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    if not path.exists() or not path.is_dir():
        return None
    return path


def discover_project_documents(max_docs: int = 8, external_repo_root: str = "", iic1_root: str = "") -> list[str]:
    root = _project_root()
    external_root = _normalize_repo_root(
        external_repo_root or os.getenv("NOUSE_KICKSTART_REPO", _DEFAULT_REPO_ROOT)
    )
    iic1 = _normalize_repo_root(
        iic1_root or os.getenv("NOUSE_IIC1_ROOT", _DEFAULT_IIC1_ROOT)
    )
    candidates: list[tuple[Path, str]] = [
        (root / "README.md", "b76"),
        (root / "STUDY_PROTOCOL.md", "b76"),
    ]
    if external_root is not None:
        candidates.extend(
            [
                (external_root / "README.md", "gh"),
                (external_root / "brian" / "README.md", "gh"),
                (external_root / "AGENTS.md", "gh"),
            ]
        )
    candidates.extend(
        [
            (root / "docs" / "FINDINGS_INDEX.md", "b76"),
            (root / "docs" / "ROADMAP_RESEARCH_TO_RELEASE.md", "b76"),
            (root / "docs" / "LAUNCH_CHECKLIST.md", "b76"),
            (root / "docs" / "GO_NO_GO_CRITERIA.md", "b76"),
            (root / "docs" / "PAPER_OUTLINE.md", "b76"),
        ]
    )
    if iic1 is not None:
        candidates.extend(
            [
                (iic1 / "workspace" / "Base76_Research_Lab" / "README.md", "iic1"),
                (iic1 / "workspace" / "Base76_Research_Lab" / "research" / "research_dashboard.md", "iic1"),
                (iic1 / "workspace" / "Base76_Research_Lab" / "operations" / "2026" / "README.md", "iic1"),
                (iic1 / "workspace" / "Base76_Research_Lab" / "operations" / "COCKPIT" / "AI_TOOL_ROUTING_POLICY.md", "iic1"),
                (iic1 / "workspace" / "Base76_Research_Lab" / "operations" / "COCKPIT" / "ACTIVE.todo", "iic1"),
            ]
        )
    out: list[str] = []
    for path, prefix in candidates:
        if path.exists() and path.is_file():
            try:
                if prefix in ("gh",) and external_root is not None:
                    rel = path.relative_to(external_root)
                elif prefix == "iic1" and iic1 is not None:
                    rel = path.relative_to(iic1)
                else:
                    rel = path.relative_to(root)
                out.append(f"{prefix}:{rel.as_posix()}")
            except Exception:
                out.append(path.as_posix())
        if len(out) >= max(1, int(max_docs)):
            break
    return out


def build_kickstart_seed_tasks(
    *,
    mission: str,
    focus_domains: list[str],
    docs: list[str],
    max_tasks: int,
) -> list[dict[str, Any]]:
    clean_mission = str(mission or "").strip() or _DEFAULT_MISSION
    docs_text = ", ".join(docs[:4]) if docs else "README.md"
    focus_text = ", ".join(x.strip() for x in focus_domains if str(x).strip()) or "autonomy, chat"

    tasks: list[dict[str, Any]] = []
    for idx, tpl in enumerate(_AGENT_TEMPLATES, start=1):
        if len(tasks) >= max(1, int(max_tasks)):
            break
        role = tpl["name"]
        prio = max(0.45, 0.95 - (idx - 1) * 0.08)
        query = (
            f"[{role}] Mission: {clean_mission}. "
            f"Fokusdomaner: {focus_text}. "
            f"Analysera och foresla nasta konkreta steg utifran {docs_text}. "
            f"Leverabel: {tpl['deliverable']}."
        )
        tasks.append(
            {
                "domain": "kickoff",
                "concepts": ["b76", role, "project_bootstrap"],
                "query": query,
                "rationale": f"Kickstart-agent for {tpl['focus']}.",
                "priority": round(prio, 3),
                "gap_type": f"kickoff_{role}",
                "source": "kickstart_v1",
            }
        )
    return tasks


def run_kickstart_bootstrap(
    *,
    field: FieldSurface,
    session_id: str = "main",
    mission: str = "",
    focus_domains: list[str] | None = None,
    max_tasks: int = 8,
    max_docs: int = 8,
    repo_root: str = "",
    iic1_root: str = "",
    source: str = "operator_kickstart",
) -> dict[str, Any]:
    sid = str(session_id or "main").strip() or "main"
    clean_mission = str(mission or "").strip() or _DEFAULT_MISSION
    domains = [str(x).strip() for x in (focus_domains or []) if str(x).strip()]

    effective_repo_root = (
        str(repo_root or "").strip()
        or str(os.getenv("NOUSE_KICKSTART_REPO", _DEFAULT_REPO_ROOT)).strip()
    )
    docs = discover_project_documents(
        max_docs=max_docs,
        external_repo_root=effective_repo_root,
        iic1_root=str(iic1_root or "").strip(),
    )
    seed_tasks = build_kickstart_seed_tasks(
        mission=clean_mission,
        focus_domains=domains,
        docs=docs,
        max_tasks=max_tasks,
    )
    added = enqueue_gap_tasks(
        field,
        max_new=max_tasks,
        seed_tasks=seed_tasks,
        detect_gaps=False,
    )

    enqueue_system_event(
        (
            "Kickstart initierad. "
            f"Mission: {clean_mission}. "
            f"Fokusdomaner: {', '.join(domains) if domains else 'autonomy, chat'}. "
            f"Repo-root: {effective_repo_root}. "
            f"Dokumentunderlag: {', '.join(docs) if docs else 'saknas'}."
        ),
        session_id=sid,
        source=source,
        context_key="kickstart_bootstrap",
    )
    request_wake(reason="kickstart_bootstrap", session_id=sid, source=source)

    return {
        "ok": True,
        "session_id": sid,
        "mission": clean_mission,
        "repo_root": effective_repo_root,
        "focus_domains": domains,
        "docs": docs,
        "seeded": len(seed_tasks),
        "added": len(added),
        "added_tasks": [
            {
                "id": int(t.get("id", 0) or 0),
                "gap_type": str(t.get("gap_type") or ""),
                "priority": float(t.get("priority", 0.0) or 0.0),
                "domain": str(t.get("domain") or ""),
            }
            for t in added
        ],
        "queue": queue_stats(),
    }
