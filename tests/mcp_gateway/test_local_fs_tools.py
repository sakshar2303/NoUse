from __future__ import annotations

from pathlib import Path

from nouse.mcp_gateway.gateway import (
    find_local_files,
    list_local_mounts,
    read_local_file,
    search_local_text,
)


def test_list_local_mounts_returns_list():
    out = list_local_mounts()
    assert "mounts" in out
    assert isinstance(out["mounts"], list)


def test_find_and_read_local_file(tmp_path: Path):
    root = tmp_path / "research"
    root.mkdir(parents=True, exist_ok=True)
    f = root / "The Shared Mind.md"
    f.write_text("title: The Shared Mind\n\nfield nodes and cognition\n", encoding="utf-8")

    found = find_local_files(
        "shared",
        roots=[str(tmp_path)],
        extensions=["md"],
        max_results=10,
    )
    paths = {row["path"] for row in found["results"]}
    assert str(f.resolve()) in paths

    read = read_local_file(str(f), max_chars=1000)
    assert read["path"] == str(f.resolve())
    assert "field nodes and cognition" in read["content"]
    assert read["truncated"] is False


def test_search_local_text_finds_match(tmp_path: Path):
    paper = tmp_path / "papers" / "fnc_notes.txt"
    paper.parent.mkdir(parents=True, exist_ok=True)
    paper.write_text(
        "intro\n"
        "FNC explores uncertainty and structured observability.\n"
        "outro\n",
        encoding="utf-8",
    )

    out = search_local_text("uncertainty", roots=[str(tmp_path)], max_results=5)
    assert out["provider"] in {"rg", "python_fallback"}
    assert out["results"]
    assert any("uncertainty" in row["snippet"].lower() for row in out["results"])

