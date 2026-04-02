from __future__ import annotations

from pathlib import Path

from nouse.llm.model_capabilities import (
    filter_tool_capable_models,
    is_tools_unsupported_error,
    load_capabilities,
    mark_model_tools_supported,
    mark_model_tools_unsupported,
)


def test_filter_tool_capable_models_skips_known_unsupported(tmp_path: Path):
    path = tmp_path / "model_capabilities.json"
    mark_model_tools_unsupported("ollama/deepseek-r1:1.5b", reason="does not support tools", path=path)
    allowed, skipped = filter_tool_capable_models(
        ["ollama/deepseek-r1:1.5b", "ollama/qwen3.5:latest"],
        path=path,
    )
    assert allowed == ["ollama/qwen3.5:latest"]
    assert skipped == ["ollama/deepseek-r1:1.5b"]


def test_mark_model_tools_supported_restores_model(tmp_path: Path):
    path = tmp_path / "model_capabilities.json"
    mark_model_tools_unsupported("m1", reason="does not support tools", path=path)
    mark_model_tools_supported("m1", path=path)
    allowed, skipped = filter_tool_capable_models(["m1"], path=path)
    assert allowed == ["m1"]
    assert skipped == []
    state = load_capabilities(path)
    assert (state.get("models") or {}).get("m1", {}).get("supports_tools") is True


def test_is_tools_unsupported_error_detects_common_marker():
    assert is_tools_unsupported_error("registry.ollama.ai/model does not support tools")
    assert not is_tools_unsupported_error("connection refused")
