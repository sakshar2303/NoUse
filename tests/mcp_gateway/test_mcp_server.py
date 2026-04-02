from __future__ import annotations

from pathlib import Path


def test_mcp_server_module_loads():
    from nouse.mcp_gateway import server

    assert server.mcp is not None
    assert callable(server.run_stdio)


def test_mcp_kernel_tools_via_server(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NOUSE_MEMORY_DIR", str(tmp_path / "memory"))

    from nouse.mcp_gateway import server

    ident = server.kernel_get_identity_tool()
    assert "mission" in ident

    write = server.kernel_write_episode_tool(
        text="Kernel server smoke memory entry.",
        source="test_server",
        domain_hint="testing",
    )
    assert write.get("status") == "ok"

    found = server.kernel_retrieve_memory_tool("smoke", limit=5)
    assert found.get("results")
