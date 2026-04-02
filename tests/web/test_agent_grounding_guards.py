from __future__ import annotations

import nouse.web.server as ws


def test_identity_queries_do_not_use_simple_fact_shortcut():
    assert ws._is_identity_query("vem är jag")  # noqa: SLF001
    assert not ws._is_simple_fact_query("vem är jag")  # noqa: SLF001
    assert ws._is_simple_fact_query("vem är kung i sverige")  # noqa: SLF001
    assert ws._is_search_info_query("vad skulle du uppdatera i systemet?")  # noqa: SLF001
    assert ws._is_search_info_query("kan du söka över disken och hitta papers?")  # noqa: SLF001
    assert not ws._is_search_info_query("vem är kung i sverige")  # noqa: SLF001


def test_ground_capability_denials_rewrites_local_fs_disclaimer():
    caps = {"local_fs": True, "web": True, "graph_write": True}
    answer = "Jag har ingen filsystemåtkomst och kan inte läsa filer på din dator."
    grounded = ws._ground_capability_denials(answer, caps)  # noqa: SLF001
    assert "list_local_mounts" in grounded
    assert "read-only" in grounded


class _FakeField:
    def domains(self):
        return ["User", "AI"]

    def concepts(self, domain=None):
        if domain is None:
            return [
                {"name": "Björn Wikström", "domain": "User"},
                {"name": "CognOS", "domain": "AI"},
            ]
        if domain == "User":
            return [{"name": "Björn Wikström"}]
        return []

    def out_relations(self, name):
        if name == "Björn Wikström":
            return [
                {"type": "bygger", "target": "FNC"},
                {"type": "bygger", "target": "CognOS"},
            ]
        return []

    def concept_knowledge(self, name):
        if name == "Björn Wikström":
            return {"summary": "Arbetar i skärningspunkten filosofi, AI och systemdesign."}
        return {"summary": ""}

    def node_context_for_query(self, query, limit=5):
        return [
            {
                "name": "Björn Wikström",
                "summary": "Arbetar i skärningspunkten filosofi, AI och systemdesign.",
            }
        ][:limit]


def test_identity_answer_from_graph_uses_user_domain_snapshot():
    answer = ws._identity_answer_from_graph(_FakeField())  # noqa: SLF001
    assert answer is not None
    assert "Björn Wikström" in answer
    assert "domän: User" in answer
    assert "filosofi, AI och systemdesign" in answer
    assert "FNC" in answer


class _FakeFieldUsernameFallback:
    def concepts(self, domain=None):
        rows = [
            {"name": "Björn Wikström", "domain": "forskning"},
            {"name": "CognOS", "domain": "AI"},
        ]
        if domain is None:
            return rows
        return [{"name": r["name"]} for r in rows if r.get("domain") == domain]

    def out_relations(self, name):
        if name == "Björn Wikström":
            return [{"type": "bygger", "target": "FNC"}]
        return []

    def concept_knowledge(self, name):
        if name == "Björn Wikström":
            return {"summary": "Forskningsarkitekt inom AI och epistemik."}
        return {"summary": ""}


def test_identity_answer_from_graph_falls_back_to_username(monkeypatch):
    monkeypatch.setenv("USER", "bjorn")
    answer = ws._identity_answer_from_graph(_FakeFieldUsernameFallback())  # noqa: SLF001
    assert answer is not None
    assert "Björn Wikström" in answer
    assert "domän: forskning" in answer


def test_system_search_info_snapshot_includes_graph_hits():
    caps = {"local_fs": False, "web": True, "graph_write": True}
    text = ws._system_search_info_snapshot(  # noqa: SLF001
        field=_FakeField(),
        query="vad vet du om björn och fnc",
        caps=caps,
    )
    assert "SYSTEM_SEARCH_INFO" in text
    assert "Grafträffar" in text
    assert "Björn Wikström" in text


def test_tool_source_bucket_classifies_graph_and_web_tools():
    assert ws._tool_source_bucket("list_domains") == "graph"  # noqa: SLF001
    assert ws._tool_source_bucket("explore_concept") == "graph"  # noqa: SLF001
    assert ws._tool_source_bucket("web_search") == "web"  # noqa: SLF001
    assert ws._tool_source_bucket("fetch_url") == "web"  # noqa: SLF001
    assert ws._tool_source_bucket("read_local_file") == "local"  # noqa: SLF001
    assert ws._tool_source_bucket("unknown_tool") == "other"  # noqa: SLF001


def test_missing_triangulation_sources_reports_graph_and_web():
    missing = ws._missing_triangulation_sources(  # noqa: SLF001
        {"local"},
        require_graph=True,
        require_web=True,
    )
    assert missing == ["graf", "webb"]
    missing_graph_only = ws._missing_triangulation_sources(  # noqa: SLF001
        {"graph"},
        require_graph=True,
        require_web=False,
    )
    assert missing_graph_only == []


def test_looks_like_triangulated_response_requires_all_sections():
    ok = """
    LLM:
    - intern punkt
    System/Graf:
    - grafpunkt
    Extern:
    - webbkalla
    Syntes:
    - slutsats
    """
    assert ws._looks_like_triangulated_response(ok)  # noqa: SLF001
    bad = "LLM: x\nSystem/Graf: y\nSyntes: z"
    assert not ws._looks_like_triangulated_response(bad)  # noqa: SLF001


def test_graph_action_request_detection():
    assert ws._is_graph_action_request(  # noqa: SLF001
        "lägg till ny nod i grafen och koppla den till AI"
    )
    assert ws._is_graph_action_request(  # noqa: SLF001
        "add relation mellan model och evidence i graph"
    )
    assert not ws._is_graph_action_request(  # noqa: SLF001
        "vad är skillnaden mellan ai och llm?"
    )


def test_confirmation_prompt_detection():
    assert ws._looks_like_confirmation_prompt(  # noqa: SLF001
        "Vänligen bekräfta: vill du att jag fortsätter?"
    )
    assert ws._looks_like_confirmation_prompt(  # noqa: SLF001
        "Vad ska vi prioritera?"
    )
    assert not ws._looks_like_confirmation_prompt(  # noqa: SLF001
        "Jag har nu lagt till noden och relationerna."
    )
