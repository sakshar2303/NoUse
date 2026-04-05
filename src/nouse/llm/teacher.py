"""
nouse.llm.teacher — LLM som kunskapskälla, NoUse som subjekt
=============================================================

Inverterad arkitektur: NoUse är hjärnan. LLM är larynxen.

Traditionell wrapper:  LLM(kärna) → NoUse(tillbehör)
NoUse Frontier:        NoUse(kärna) → LLM(röst/extraktionsverktyg)

Flöde:
  1. NoUse identifierar ett kunskapsgap (låg konfidens i grafen)
  2. LLM tillfrågas om sin parametriska kunskap om gapet
  3. Svaret dekonstrueras till (src, rel_type, tgt, why)-tupler
  4. Varje tupel utvärderas bayesianskt via evidence.py
  5. Validerade relationer → learning_coordinator.on_fact()
  6. Svaga relationer → eskalator-kö för webvalidering

LLM:en vet inte vem den är. NoUse vet.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from nouse.field.surface import FieldSurface
    from nouse.learning_coordinator import LearningCoordinator

from nouse.daemon.evidence import assess_relation

_log = logging.getLogger("nouse.teacher")

# ── Konfiguration ─────────────────────────────────────────────────────────────

TEACHER_BASE_URL    = os.getenv("NOUSE_TEACHER_BASE_URL", "https://models.inference.ai.azure.com")
TEACHER_TOKEN       = os.getenv("GITHUB_TOKEN", "")
TEACHER_MODEL       = os.getenv("NOUSE_TEACHER_MODEL", "gpt-4o")
TEACHER_TIMEOUT     = float(os.getenv("NOUSE_TEACHER_TIMEOUT_SEC", "30.0"))
TEACHER_MIN_SCORE   = float(os.getenv("NOUSE_TEACHER_MIN_SCORE", "0.52"))   # indikation+
TEACHER_MAX_RELS    = int(os.getenv("NOUSE_TEACHER_MAX_RELATIONS", "12"))

# ── Datastrukturer ────────────────────────────────────────────────────────────

@dataclass
class TeacherRelation:
    src: str
    rel_type: str
    tgt: str
    why: str
    domain_src: str = "general"
    domain_tgt: str = "general"
    evidence_score: float = 0.0
    tier: str = "hypotes"
    learned: bool = False


@dataclass
class TeachResult:
    concept: str
    relations: list[TeacherRelation] = field(default_factory=list)
    learned_count: int = 0
    skipped_count: int = 0
    model_used: str = ""
    error: str | None = None


# ── Extraktionsprompt ────────────────────────────────────────────────────────

_EXTRACT_PROMPT = """\
Du är ett kunskapsextraktionsverktyg. Din uppgift är att extrahera strukturella \
relationer ur din träningskunskap om ett givet koncept.

Koncept: "{concept}"
Domän-kontext: "{domain}"

Svara ENBART med ett JSON-objekt på formen:
{{
  "relations": [
    {{
      "src": "källkoncept",
      "rel_type": "relationstyp",
      "tgt": "målkoncept",
      "why": "mekanistisk motivering — varför gäller denna relation?",
      "domain_src": "domän för src",
      "domain_tgt": "domän för tgt"
    }}
  ]
}}

Regler:
- Max {max_relations} relationer
- rel_type ska vara mekanistisk: "orsakar", "möjliggör", "reglerar", "är_del_av", 
  "predikterar", "begränsar", "emergerar_ur", "korrelerar_med", "konvergerar_i"
- why ska vara substantiell (≥40 tecken), mekanistisk, inte tautologisk
- Prioritera korsdomän-relationer (neuroscience↔matematik, fysik↔kognition etc)
- Inkludera INTE triviala eller cirkulära relationer
- Om du är osäker på en relation — utelämna den hellre än att gissa
"""


# ── GitHub Models / OpenAI-compatible klient ─────────────────────────────────

async def _call_teacher_llm(concept: str, domain: str) -> list[dict]:
    """
    Fråga teacher-LLM om dess parametriska kunskap.
    Returnerar rå relationsdict-lista eller tom lista vid fel.
    """
    token = TEACHER_TOKEN
    if not token:
        _log.warning("GITHUB_TOKEN saknas — teacher LLM ej tillgänglig")
        return []

    prompt = _EXTRACT_PROMPT.format(
        concept=concept,
        domain=domain,
        max_relations=TEACHER_MAX_RELS,
    )

    payload = {
        "model": TEACHER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,   # låg temp — vi vill ha strukturell precision
        "max_tokens": 1500,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=TEACHER_TIMEOUT) as client:
            r = await client.post(
                f"{TEACHER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
        if r.status_code != 200:
            _log.warning("Teacher LLM HTTP %d: %s", r.status_code, r.text[:200])
            return []

        content = r.json()["choices"][0]["message"]["content"]
        start = content.find("{")
        end = content.rfind("}") + 1
        if start < 0 or end <= start:
            return []
        data = json.loads(content[start:end])
        return data.get("relations", [])

    except Exception as e:
        _log.warning("Teacher LLM anrop misslyckades: %s", e)
        return []


# ── Kunskapsvalidering och inlärning ─────────────────────────────────────────

def _validate_and_score(raw: dict) -> TeacherRelation | None:
    """
    Validera och evidensbedöm en rårelation från LLM.
    Returnerar None om relationen är ogiltig.
    """
    src = str(raw.get("src") or "").strip()
    tgt = str(raw.get("tgt") or "").strip()
    rel_type = str(raw.get("rel_type") or "").strip()
    why = str(raw.get("why") or "").strip()
    domain_src = str(raw.get("domain_src") or "general").strip()
    domain_tgt = str(raw.get("domain_tgt") or "general").strip()

    # Grundläggande validering
    if not src or not tgt or not rel_type:
        return None
    if src.lower() == tgt.lower():
        return None   # cirkulär
    if len(why) < 20:
        return None   # för tunn motivering

    # Bayesiansk evidensbedömning via befintlig evidence.py
    assessment = assess_relation(
        relation={
            "src": src,
            "tgt": tgt,
            "type": rel_type,
            "why": why,
            "domain_src": domain_src,
            "domain_tgt": domain_tgt,
        }
    )

    # Bonus för korsdomän (LLM:ens styrka är bredd)
    score = assessment.score
    if domain_src != domain_tgt:
        score = min(1.0, score + 0.05)

    return TeacherRelation(
        src=src,
        rel_type=rel_type,
        tgt=tgt,
        why=why,
        domain_src=domain_src,
        domain_tgt=domain_tgt,
        evidence_score=round(score, 3),
        tier=assessment.tier,
    )


# ── Huvud-API ────────────────────────────────────────────────────────────────

async def teach_concept(
    concept: str,
    field: "FieldSurface",
    coordinator: "LearningCoordinator",
    *,
    domain: str = "general",
    min_score: float = TEACHER_MIN_SCORE,
    dry_run: bool = False,
) -> TeachResult:
    """
    NoUse frågar LLM om sin parametriska kunskap om ett koncept.
    Validerade relationer lärs direkt in i grafen.

    Args:
        concept:     Konceptet NoUse vill lära sig mer om
        field:       FieldSurface — grafen som skrivs till
        coordinator: LearningCoordinator — hebbisk plastisitet
        domain:      Domänkontext för konceptet
        min_score:   Minsta evidenspoäng för direkt inlärning (default: 0.52 = indikation)
        dry_run:     Om True — validera men skriv inte till grafen

    Returns:
        TeachResult med statistik och alla relationer (lärda + avvisade)
    """
    result = TeachResult(concept=concept, model_used=TEACHER_MODEL)

    _log.info("teach_concept('%s', domain='%s', model=%s)", concept, domain, TEACHER_MODEL)

    # Steg 1: Fråga LLM
    raw_relations = await _call_teacher_llm(concept, domain)
    if not raw_relations:
        result.error = "LLM returnerade inga relationer"
        return result

    _log.info("LLM returnerade %d rårelationer för '%s'", len(raw_relations), concept)

    # Steg 2: Validera och evidensbedöm varje relation
    for raw in raw_relations:
        rel = _validate_and_score(raw)
        if rel is None:
            result.skipped_count += 1
            continue

        result.relations.append(rel)

        if rel.evidence_score < min_score:
            # Under tröskeln — flagga för eventuell webvalidering
            _log.debug("Avvisad (score=%.3f): %s -[%s]-> %s", rel.evidence_score, rel.src, rel.rel_type, rel.tgt)
            result.skipped_count += 1
            continue

        if dry_run:
            rel.learned = False
            result.learned_count += 1
            continue

        # Steg 3: Skriv till graf + aktivera hebbisk plastisitet
        try:
            field.add_concept(rel.src, domain=rel.domain_src, source="llm_teacher")
            field.add_concept(rel.tgt, domain=rel.domain_tgt, source="llm_teacher")
            field.add_relation(
                src=rel.src,
                rel_type=rel.rel_type,
                tgt=rel.tgt,
                why=f"[llm_teacher:{TEACHER_MODEL}] {rel.why}",
                evidence_score=rel.evidence_score,
                source_tag="llm_teacher",
            )
            coordinator.on_fact(
                rel.src,
                rel.rel_type,
                rel.tgt,
                why=rel.why,
                evidence_score=rel.evidence_score,
                support_count=1,
            )
            rel.learned = True
            result.learned_count += 1
            _log.info("Lärd: %s -[%s]-> %s (score=%.3f, tier=%s)",
                      rel.src, rel.rel_type, rel.tgt, rel.evidence_score, rel.tier)

        except Exception as e:
            _log.warning("Kunde inte lära relation: %s", e)
            result.skipped_count += 1

    _log.info(
        "teach_concept klar: %d lärda, %d avvisade",
        result.learned_count, result.skipped_count,
    )
    return result


async def teach_from_answer(
    question: str,
    answer: str,
    field: "FieldSurface",
    coordinator: "LearningCoordinator",
    *,
    domain: str = "general",
    min_score: float = TEACHER_MIN_SCORE,
) -> TeachResult:
    """
    NoUse lär sig av ett befintligt LLM-svar — utan extra API-anrop.
    Extraherar relationer direkt ur svarstexten.

    Används när NoUse redan fått ett svar och vill konsolidera kunskapen.
    """
    result = TeachResult(concept=question, model_used="from_answer")

    # Extraktionsprompt för befintligt svar
    extract_prompt = f"""\
Extrahera strukturella kunskapsrelationer ur detta svar.

Fråga: {question}
Svar: {answer[:2000]}

Svara ENBART med JSON:
{{
  "relations": [
    {{"src": "...", "rel_type": "...", "tgt": "...", "why": "...", 
      "domain_src": "...", "domain_tgt": "..."}}
  ]
}}

Max 8 relationer. Mekanistiska, inte triviala.
"""
    token = TEACHER_TOKEN
    if not token:
        result.error = "GITHUB_TOKEN saknas"
        return result

    try:
        async with httpx.AsyncClient(timeout=TEACHER_TIMEOUT) as client:
            r = await client.post(
                f"{TEACHER_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "model": TEACHER_MODEL,
                    "messages": [{"role": "user", "content": extract_prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1000,
                },
            )
        if r.status_code != 200:
            result.error = f"HTTP {r.status_code}"
            return result

        content = r.json()["choices"][0]["message"]["content"]
        start = content.find("{")
        end = content.rfind("}") + 1
        if start < 0:
            result.error = "Ingen JSON i svar"
            return result
        raw_relations = json.loads(content[start:end]).get("relations", [])

    except Exception as e:
        result.error = str(e)
        return result

    # Samma validerings-pipeline som teach_concept
    for raw in raw_relations:
        rel = _validate_and_score(raw)
        if rel is None or rel.evidence_score < min_score:
            result.skipped_count += 1
            continue
        try:
            field.add_concept(rel.src, domain=rel.domain_src, source="llm_teacher_answer")
            field.add_concept(rel.tgt, domain=rel.domain_tgt, source="llm_teacher_answer")
            field.add_relation(
                src=rel.src,
                rel_type=rel.rel_type,
                tgt=rel.tgt,
                why=f"[from_answer] {rel.why}",
                evidence_score=rel.evidence_score,
                source_tag="llm_teacher_answer",
            )
            coordinator.on_fact(
                rel.src, rel.rel_type, rel.tgt,
                why=rel.why, evidence_score=rel.evidence_score,
            )
            rel.learned = True
            result.learned_count += 1
        except Exception as e:
            _log.warning("Relation kunde inte läras: %s", e)
            result.skipped_count += 1

    return result
