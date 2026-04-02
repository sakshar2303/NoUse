from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

import anyio
import pytest


def _extract_json_payload(result: object) -> dict:
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return {}


async def _run_mcp_stdio_external_client_roundtrip(tmp_path) -> None:
    mcp = pytest.importorskip("mcp")

    StdioServerParameters = getattr(mcp, "StdioServerParameters")
    ClientSession = getattr(mcp, "ClientSession")

    try:
        from mcp.client.stdio import stdio_client
    except Exception as exc:  # pragma: no cover - env-dependent import path
        pytest.skip(f"mcp stdio client unavailable: {exc}")

    memory_dir = tmp_path / "memory"
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["NOUSE_MEMORY_DIR"] = str(memory_dir)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{repo_root}:{existing_pythonpath}" if existing_pythonpath else str(repo_root)
    )

    b76_cmd = shutil.which("b76")
    if not b76_cmd:
        pytest.skip("b76 CLI executable not found in PATH")

    server = StdioServerParameters(
        command=b76_cmd,
        args=["mcp", "serve"],
        env=env,
        cwd=str(repo_root),
    )

    marker = f"mcp-e2e-{uuid.uuid4().hex[:10]}"

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert "kernel_get_identity_tool" in tool_names
            assert "kernel_write_episode_tool" in tool_names

            identity_result = await session.call_tool("kernel_get_identity_tool", {})
            identity_payload = _extract_json_payload(identity_result)
            assert "mission" in identity_payload

            write_result = await session.call_tool(
                "kernel_write_episode_tool",
                {
                    "text": f"External MCP E2E {marker}",
                    "source": "pytest_e2e",
                    "domain_hint": "testing",
                },
            )
            write_payload = _extract_json_payload(write_result)
            assert write_payload.get("status") == "ok"

            retrieve_result = await session.call_tool(
                "kernel_retrieve_memory_tool",
                {"query": marker, "limit": 5},
            )
            retrieve_payload = _extract_json_payload(retrieve_result)
            results = retrieve_payload.get("results") or []
            assert results

            guarded_result = await session.call_tool(
                "kernel_execute_self_update_tool",
                {"plan": "dry-run no approval token"},
            )
            guarded_payload = _extract_json_payload(guarded_result)
            blocked = guarded_payload.get("status") == "blocked" or guarded_payload.get("error") == "guarded_write_blocked"
            assert blocked
            policy_hint = (guarded_payload.get("reason") or "") + " " + str(
                (guarded_payload.get("policy") or {}).get("requires", "")
            )
            assert "approval" in policy_hint.lower() or "guarded" in policy_hint.lower()


def test_mcp_stdio_external_client_roundtrip(tmp_path):
    anyio.run(_run_mcp_stdio_external_client_roundtrip, tmp_path)