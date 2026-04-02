"""
b76.plugins.loader — Plugin-livscykel + runtime-laddning
=========================================================
Stödjer:
- upptäckt/laddning av plugins (inbyggda + användarinstallerade),
- registry med versionsspårning,
- install/remove/update för lokala plugin-filer.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import shutil
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("nouse.plugins")

RUNTIME_PLUGIN_DIR = Path.home() / ".local" / "share" / "nouse" / "plugins"
PLUGIN_REGISTRY_PATH = Path.home() / ".local" / "share" / "nouse" / "plugin_registry.json"

# name -> {"schema": dict, "execute": callable, "module": str, "source": str, "version": str}
_PLUGINS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _builtin_plugin_dir() -> Path:
    return Path(__file__).parent


def _registry_blank() -> dict[str, Any]:
    return {"version": 1, "plugins": {}, "updated_at": ""}


def _load_registry(path: Path = PLUGIN_REGISTRY_PATH) -> dict[str, Any]:
    if not path.exists():
        return _registry_blank()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _registry_blank()
    if not isinstance(raw, dict):
        return _registry_blank()
    raw.setdefault("plugins", {})
    return raw


def _save_registry(state: dict[str, Any], path: Path = PLUGIN_REGISTRY_PATH) -> dict[str, Any]:
    out = _registry_blank()
    out["version"] = int(state.get("version", 1) or 1)
    plugins = state.get("plugins")
    out["plugins"] = plugins if isinstance(plugins, dict) else {}
    out["updated_at"] = str(state.get("updated_at") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _safe_plugin_name(raw: str) -> str:
    name = str(raw or "").strip().lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = name.strip("_")
    return name[:64] if name else ""


def _iter_plugin_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    builtins = _builtin_plugin_dir()
    for py_file in builtins.glob("*.py"):
        if py_file.name in {"__init__.py", "loader.py"}:
            continue
        files.append((py_file, "builtin"))
    if RUNTIME_PLUGIN_DIR.exists():
        for py_file in RUNTIME_PLUGIN_DIR.glob("*.py"):
            files.append((py_file, "runtime"))
    return files


def load_plugins() -> None:
    """
    Söker igenom plugin-kataloger och laddar/omladdar verktyg.
    """
    global _PLUGINS
    with _LOCK:
        _PLUGINS.clear()
        registry = _load_registry()
        known = registry.get("plugins") if isinstance(registry.get("plugins"), dict) else {}
        for py_file, source in _iter_plugin_files():
            module_name = py_file.stem
            try:
                spec = importlib.util.spec_from_file_location(f"nouse.plugins.{module_name}", py_file)
                if not spec or not spec.loader:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if not hasattr(module, "TOOL_SCHEMA") or not hasattr(module, "execute"):
                    log.warning("Plugin %s saknar TOOL_SCHEMA eller execute()", py_file.name)
                    continue
                schema = getattr(module, "TOOL_SCHEMA")
                executable = getattr(module, "execute")
                if not isinstance(schema, dict):
                    log.warning("Plugin %s har ogiltigt TOOL_SCHEMA", py_file.name)
                    continue
                tool_name = schema.get("function", {}).get("name", module_name)
                reg = known.get(tool_name) if isinstance(known, dict) else {}
                version = getattr(module, "PLUGIN_VERSION", None) or (reg or {}).get("version") or "0.1.0"
                description = getattr(module, "PLUGIN_DESCRIPTION", None) or (reg or {}).get("description") or ""
                _PLUGINS[tool_name] = {
                    "schema": schema,
                    "execute": executable,
                    "module": module_name,
                    "source": source,
                    "version": str(version),
                    "description": str(description),
                    "path": str(py_file),
                }
            except Exception as e:
                log.error("Krasch vid laddning av plugin %s: %s", py_file.name, e)


def get_plugin_schemas() -> list[dict]:
    if not _PLUGINS:
        load_plugins()
    return [p["schema"] for p in _PLUGINS.values()]


def is_plugin_tool(name: str) -> bool:
    if not _PLUGINS:
        load_plugins()
    return name in _PLUGINS


def execute_plugin(name: str, args: dict[str, Any]) -> Any:
    if name not in _PLUGINS:
        return {"error": f"Plugin tool {name} not found"}
    try:
        executable = _PLUGINS[name]["execute"]
        return executable(**args)
    except Exception as e:
        log.error("Fel vid körning av plugin %s: %s", name, e)
        return {"error": str(e)}


def list_plugins() -> list[dict[str, Any]]:
    if not _PLUGINS:
        load_plugins()
    rows = []
    for name, row in _PLUGINS.items():
        rows.append(
            {
                "name": name,
                "version": str(row.get("version") or "0.1.0"),
                "source": str(row.get("source") or "unknown"),
                "module": str(row.get("module") or ""),
                "description": str(row.get("description") or ""),
                "path": str(row.get("path") or ""),
            }
        )
    rows.sort(key=lambda r: (r["source"], r["name"]))
    return rows


def install_plugin(
    source_path: str,
    *,
    name: str = "",
    version: str = "0.1.0",
    description: str = "",
) -> dict[str, Any]:
    src = Path(source_path).expanduser().resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Pluginfil hittades inte: {src}")
    if src.suffix.lower() != ".py":
        raise ValueError("Plugin måste vara en .py-fil")
    plugin_name = _safe_plugin_name(name or src.stem)
    if not plugin_name:
        raise ValueError("Ogiltigt pluginnamn")

    RUNTIME_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    dst = RUNTIME_PLUGIN_DIR / f"{plugin_name}.py"
    shutil.copy2(src, dst)

    with _LOCK:
        state = _load_registry()
        plugins = state.setdefault("plugins", {})
        plugins[plugin_name] = {
            "name": plugin_name,
            "version": str(version or "0.1.0"),
            "description": str(description or ""),
            "path": str(dst),
            "installed_from": str(src),
        }
        _save_registry(state)
    load_plugins()
    return {
        "ok": True,
        "name": plugin_name,
        "version": str(version or "0.1.0"),
        "path": str(dst),
        "installed_from": str(src),
    }


def remove_plugin(name: str) -> dict[str, Any]:
    plugin_name = _safe_plugin_name(name)
    if not plugin_name:
        raise ValueError("plugin name required")
    path = RUNTIME_PLUGIN_DIR / f"{plugin_name}.py"
    removed_file = False
    if path.exists():
        path.unlink()
        removed_file = True

    with _LOCK:
        state = _load_registry()
        plugins = state.setdefault("plugins", {})
        removed_registry = plugins.pop(plugin_name, None) is not None
        _save_registry(state)
    load_plugins()
    return {"ok": True, "name": plugin_name, "removed_file": removed_file, "removed_registry": removed_registry}


def update_plugin(
    name: str,
    source_path: str,
    *,
    version: str = "",
    description: str = "",
) -> dict[str, Any]:
    plugin_name = _safe_plugin_name(name)
    if not plugin_name:
        raise ValueError("plugin name required")
    ver = str(version or "").strip()
    if not ver:
        with _LOCK:
            state = _load_registry()
            reg = (state.get("plugins") or {}).get(plugin_name) or {}
        ver = str(reg.get("version") or "0.1.0")
    return install_plugin(
        source_path,
        name=plugin_name,
        version=ver,
        description=description,
    )
