from __future__ import annotations

import json

from nouse.memory.store import MemoryStore


class DummyField:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upsert_concept_knowledge(
        self,
        name: str,
        *,
        claim: str | None = None,
        evidence_ref: str | None = None,
        related_terms: list[str] | None = None,
        uncertainty: float | None = None,
    ) -> None:
        self.calls.append(
            {
                "name": name,
                "claim": claim,
                "evidence_ref": evidence_ref,
                "related_terms": related_terms or [],
                "uncertainty": uncertainty,
            }
        )


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_ingest_episode_updates_working_and_procedural(tmp_path):
    store = MemoryStore(root=tmp_path, working_capacity=10)
    rel = {
        "src": "hippocampus",
        "type": "konsoliderar",
        "tgt": "episodiskt minne",
        "domain_src": "neurovetenskap",
        "domain_tgt": "neurovetenskap",
        "why": "minne stabiliseras over tid",
        "evidence_score": 0.82,
    }

    ep1 = store.ingest_episode(
        "Hippocampus konsoliderar episodiskt minne.",
        {"source": "paper", "domain_hint": "neurovetenskap"},
        [rel],
    )
    ep2 = store.ingest_episode(
        "Amygdala modulerar emotionell saliens.",
        {"source": "paper", "domain_hint": "neurovetenskap"},
        [
            {
                "src": "amygdala",
                "type": "modulerar",
                "tgt": "emotionell saliens",
                "domain_src": "neurovetenskap",
                "domain_tgt": "neurovetenskap",
                "evidence_score": 0.7,
            }
        ],
    )
    ep3 = store.ingest_episode(
        "Prefrontal cortex reglerar kontroll.",
        {"source": "notes", "domain_hint": "kognition"},
        [],
    )

    assert ep1["id"] and ep2["id"] and ep3["id"]
    working = _read_json(store.working_path)
    assert len(working["items"]) == 3
    assert working["items"][-1]["id"] == ep3["id"]

    procedural = _read_json(store.procedural_path)
    assert procedural["source_counts"]["paper"] == 2
    assert procedural["source_counts"]["notes"] == 1
    assert procedural["relation_type_counts"]["konsoliderar"] == 1
    assert procedural["relation_type_counts"]["modulerar"] == 1

    audit = store.audit(limit=5)
    assert audit["episodes_total"] == 3
    assert audit["unconsolidated_total"] == 3
    assert audit["working_items"] == 3
    snapshot = store.working_snapshot(limit=2)
    assert len(snapshot) == 2
    assert snapshot[0]["id"] == ep3["id"]
    assert snapshot[1]["id"] == ep2["id"]


def test_consolidate_marks_episodes_and_builds_semantic_facts(tmp_path):
    store = MemoryStore(root=tmp_path)
    rel = {
        "src": "hippocampus",
        "type": "konsoliderar",
        "tgt": "episodiskt minne",
        "domain_src": "neurovetenskap",
        "domain_tgt": "neurovetenskap",
        "why": "soker stabila minnesspar",
        "evidence_score": 0.8,
    }

    store.ingest_episode("Ett pastaende.", {"source": "paper"}, [rel])
    store.ingest_episode("Samma relation igen.", {"source": "paper"}, [rel])

    field = DummyField()
    result = store.consolidate(field, max_episodes=20, strict_min_evidence=0.65)

    assert result["processed_episodes"] == 2
    assert result["consolidated_relations"] == 2
    assert result["semantic_facts_before"] == 0
    assert result["semantic_facts_after"] == 1
    assert result["unconsolidated_after"] == 0

    semantic = _read_json(store.semantic_path)
    key = "hippocampus|konsoliderar|episodiskt minne"
    assert key in semantic["facts"]
    assert semantic["facts"][key]["support_count"] == 2
    assert semantic["facts"][key]["avg_evidence"] == 0.8
    assert len(field.calls) == 4
    assert any("episodic:" in (c["evidence_ref"] or "") for c in field.calls)

    episodes = store._load_episodes()  # noqa: SLF001 - explicit state verification in test
    assert episodes and all(bool(e.get("consolidated")) for e in episodes)


def test_consolidate_promotes_repeated_dialogue_to_long_term(tmp_path):
    store = MemoryStore(root=tmp_path)
    question = "Vad vet du om mig?"
    answer = "Du arbetar med filosofi, AI och systemdesign med fokus pa evidens."

    store.ingest_episode(
        f"Fraga: {question}\nSvar: {answer}",
        {"source": "chat_live:main", "domain_hint": "dialog"},
        [],
    )
    store.ingest_episode(
        f"Fraga: {question}\nSvar: {answer}",
        {"source": "chat_live:main", "domain_hint": "dialog"},
        [],
    )

    field = DummyField()
    result = store.consolidate(field, max_episodes=20, strict_min_evidence=0.65)

    assert result["processed_episodes"] == 2
    assert result["dialogue_promotions"] >= 1
    assert result["dialogue_facts"] >= 1
    assert any(c["name"] == "dialog_memory" for c in field.calls)
    assert any("Dialogminne:" in (c["claim"] or "") for c in field.calls)

    semantic = _read_json(store.semantic_path)
    dialogue_facts = semantic.get("dialogue_facts") or {}
    assert isinstance(dialogue_facts, dict)
    assert dialogue_facts
    one = next(iter(dialogue_facts.values()))
    assert int(one.get("support_count", 0) or 0) >= 2
    assert bool(one.get("promoted"))
