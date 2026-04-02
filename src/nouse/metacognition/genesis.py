"""
b76.metacognition.genesis — Arkitektonisk Autonomi (Tool Genesis)
=================================================================
Detta lager ger LLM-en förmågan att stiga ut ur sin ram
och skriva egna verktyg när den stöter på blockeringar.
Den kan kompilera ren Python-kod och registrera systemet dynamiskt
i b76 agent-verktygen. Även parametertuning ingår här.
"""
from __future__ import annotations

import ast
import logging
from typing import Any
from pathlib import Path

# Laddare
from nouse.plugins.loader import load_plugins

log = logging.getLogger("nouse.genesis")

GENESIS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_new_tool",
            "description": (
                "Metakognitivt larm: Systemet saknar ett verktyg. "
                "Istället för att misslyckas, SKRIV ETT EGET Python-verktyg. "
                "Denna funktion skapar en ny `.py`-fil med din kod och gör den omedelbart tillgänglig. "
                "Koden du skriver bygger på formatet: `TOOL_SCHEMA` definierad som en lista och "
                "`def execute(**kwargs)`."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "System-identifikator (a-z, underscore). t.ex. 'math_solver'",
                    },
                    "description": {
                        "type": "string",
                        "description": "Kort beskrivning av vad ditt nya verktyg gör (används för att hitta verktyget nästa cykel)",
                    },
                    "python_code": {
                        "type": "string",
                        "description": (
                            "KOMPLETT FULLSTÄNDIG Python-kod som måste innehålla: \n"
                            "1. Imports\n"
                            "2. TOOL_SCHEMA = {'type': 'function', 'function': {'name': '<tool_name>', 'description': '...', 'parameters': {...}}}\n"
                            "3. def execute(**kwargs):\n"
                            "       return result_dict\n"
                        ),
                    },
                },
                "required": ["tool_name", "description", "python_code"],
            },
        },
    },
]

def is_genesis_tool(name: str) -> bool:
    """Returnerar True om det är ett formellt metakognitivt verktyg."""
    return name in ("create_new_tool", )

def execute_genesis_tool(name: str, args: dict[str, Any]) -> Any:
    """Styr anropet."""
    if name == "create_new_tool":
        return create_new_tool(
            args["tool_name"],
            args["description"],
            args["python_code"]
        )
    return {"error": f"Okänt genesis-verktyg: {name}"}

def create_new_tool(tool_name: str, description: str, python_code: str) -> dict[str, Any]:
    """Validerar och sparar ny Python-plugin i plugins/."""
    # Säkra namnet så det är en godkänd modul
    safe_name = "".join(c for c in tool_name.lower() if c.isalnum() or c == "_")
    if not safe_name:
        return {"error": "Invalid tool_name"}
        
    plugins_dir = Path(__file__).parent.parent / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    plugin_path = plugins_dir / f"{safe_name}.py"
    
    # Kör en syntax-verifiering med AST för att hindra korruption
    try:
        ast.parse(python_code)
    except SyntaxError as e:
        log.error(f"Syntax error i kodskapad plugin {safe_name}: {e}")
        return {"error": f"SyntaxError i Python koden: {e}"}
        
    try:
        plugin_path.write_text(python_code, encoding="utf-8")
        # Ber last loader'n the omvärdera pluginkatalogen
        load_plugins()
        log.warning(f"Metakognitiv Tool Genesis: Skapade `{safe_name}` plugin framgångsrikt.")
        return {
            "success": True, 
            "message": f"Verktyget '{safe_name}' är nu operativt och finns i nästa verktygsanrop.",
            "path": str(plugin_path)
        }
    except Exception as e:
        return {"error": f"Misslyckades att skriva till disk: {e}"}
