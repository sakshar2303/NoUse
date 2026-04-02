from __future__ import annotations

import nouse.web.server as ws


def test_extract_numbered_options_parses_common_formats():
    text = (
        "Vill du att jag:\n"
        "1 Skapa en user-nod\n"
        "2. Söka samband\n"
        "• 3) Lägga till relationer\n"
    )
    out = ws._extract_numbered_options(text)  # noqa: SLF001
    assert out[1].startswith("Skapa en user-nod")
    assert out[2].startswith("Söka samband")
    assert out[3].startswith("Lägga till relationer")


def test_resolve_numeric_choice_uses_remembered_session_options():
    ws._SESSION_NUMERIC_CHOICES.clear()  # noqa: SLF001
    ws._remember_numbered_options("s1", "1 Skapa user-nod\n2 Utforska domän")  # noqa: SLF001
    query, idx = ws._resolve_numeric_choice("s1", "1")  # noqa: SLF001
    assert idx == 1
    assert "Skapa user-nod" in query


def test_resolve_numeric_choice_prefers_explicit_tail_text():
    ws._SESSION_NUMERIC_CHOICES.clear()  # noqa: SLF001
    ws._remember_numbered_options("s1", "1 Skapa user-nod\n2 Utforska domän")  # noqa: SLF001
    query, idx = ws._resolve_numeric_choice("s1", "1 lägg in mig som central nod")  # noqa: SLF001
    assert idx == 1
    assert query == "lägg in mig som central nod"
