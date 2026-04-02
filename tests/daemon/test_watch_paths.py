from __future__ import annotations

from pathlib import Path

from nouse.daemon.main import _resolve_watch_paths


def test_default_watch_paths_include_repo_src(monkeypatch):
    monkeypatch.delenv("NOUSE_WATCH_PATHS", raising=False)
    monkeypatch.delenv("NOUSE_WATCH_EXTRA_PATHS", raising=False)

    paths = _resolve_watch_paths()
    expected = Path(__file__).resolve().parents[2] / "src"
    assert any(Path(p) == expected for p in paths)


def test_watch_paths_override_takes_precedence(monkeypatch):
    monkeypatch.setenv("NOUSE_WATCH_PATHS", "/tmp/a,/tmp/b")
    monkeypatch.delenv("NOUSE_WATCH_EXTRA_PATHS", raising=False)

    paths = _resolve_watch_paths()
    assert paths == [Path("/tmp/a"), Path("/tmp/b")]

