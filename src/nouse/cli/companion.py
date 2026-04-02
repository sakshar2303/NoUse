"""
nouse companion — relationellt samtalsläge för idéutbyte
======================================================
Målet är att möjliggöra kontinuerlig dialog där både människa och nouse
utvecklar en gemensam förståelse över tid.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from nouse.ollama_client.client import AsyncOllama
from nouse.trace.output_trace import (
    build_attack_plan,
    derive_assumptions,
    new_trace_id,
    record_event,
)

console = Console()

DEFAULT_CHAT_MODEL = "qwen3.5:latest"
API_INGEST = "http://127.0.0.1:8765/api/ingest"
API_STATUS = "http://127.0.0.1:8765/api/status"

COMPANION_DIR = Path.home() / ".local" / "share" / "nouse" / "companion"
USER_CONTEXT_PATH = Path(
    "/home/bjorn/projects/nouse/docs/"
    "USER_CONTEXT_BJORN_WIKSTROM.md"
)


def _daemon_running() -> bool:
    try:
        urllib.request.urlopen(API_STATUS, timeout=2)
        return True
    except Exception:
        return False


def _ingest_exchange(user_text: str, assistant_text: str, trace_id: str | None = None) -> None:
    payload_text = (
        "Companion exchange:\n"
        f"human: {user_text}\n"
        f"nouse: {assistant_text}\n"
    )
    if _daemon_running():
        _ingest_bg(payload_text, trace_id=trace_id)
    else:
        # Fallback: queue-fil som daemon plockar senare.
        qdir = Path.home() / ".local" / "share" / "nouse" / "capture_queue"
        qdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        qpath = qdir / f"companion_{ts}.txt"
        qpath.write_text(payload_text, encoding="utf-8")
        if trace_id:
            record_event(
                trace_id,
                "companion.ingest_queued",
                endpoint="cli.companion",
                payload={"queue_path": str(qpath)},
            )


def _ingest_bg(text: str, trace_id: str | None = None) -> None:
    def _do() -> None:
        try:
            payload = json.dumps({"text": text, "source": "companion_chat"}).encode()
            req = urllib.request.Request(
                API_INGEST,
                payload,
                {"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=12)
            data = json.loads(resp.read())
            if trace_id:
                record_event(
                    trace_id,
                    "companion.ingest_result",
                    endpoint="cli.companion",
                    payload={
                        "added": int(data.get("added", 0) or 0),
                        "ingest_trace_id": data.get("trace_id"),
                    },
                )
        except Exception:
            # Vi ignorerar ingest-fel i companion-läget.
            if trace_id:
                record_event(
                    trace_id,
                    "companion.ingest_error",
                    endpoint="cli.companion",
                    payload={"error": "ingest_failed"},
                )

    threading.Thread(target=_do, daemon=True).start()


def _build_system_prompt() -> str:
    profile = ""
    try:
        if USER_CONTEXT_PATH.exists():
            profile = USER_CONTEXT_PATH.read_text(encoding="utf-8", errors="ignore")[:6000]
    except OSError:
        profile = ""
    except Exception:
        profile = ""

    return (
        "Du är nouse i companion-läge.\n"
        "Målet är dialog, idéutbyte och gemensamt lärande med Björn.\n"
        "Var varm, nyfiken, tydlig och konkret.\n"
        "Hjälp till att:\n"
        "1) förfina idéer,\n"
        "2) skilja evidens från antaganden,\n"
        "3) föreslå nästa experimentsteg.\n"
        "Svara på svenska.\n"
        "Om något är osäkert: säg det uttryckligen.\n\n"
        "Användarkontext:\n"
        f"{profile if profile else '(ingen profilfil hittad)'}"
    )


def _write_session_log(turns: list[tuple[str, str]]) -> Path:
    COMPANION_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    path = COMPANION_DIR / f"session_{ts}.md"
    lines = [
        f"# nouse Companion Session — {ts}",
        "",
        f"Turns: {len(turns)}",
        "",
    ]
    for i, (u, a) in enumerate(turns, 1):
        lines.append(f"## Turn {i}")
        lines.append(f"**Björn:** {u}")
        lines.append("")
        lines.append(f"**nouse:** {a}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _resolve_model(model: str | None = None) -> str:
    """
    Prioritet:
    1) --model flagga
    2) NOUSE_COMPANION_MODEL
    3) DEFAULT_CHAT_MODEL
    """
    if model and model.strip():
        return model.strip()
    env_model = os.getenv("NOUSE_COMPANION_MODEL", "").strip()
    if env_model:
        return env_model
    return DEFAULT_CHAT_MODEL


def _resolve_profile(profile: str | None = None) -> dict[str, object]:
    """
    Companion-profiler:
    - fast: snabb respons, låg token-budget
    - balanced: standard
    - deep: längre och mer utforskande svar
    """
    raw = (profile or os.getenv("NOUSE_COMPANION_PROFILE") or "balanced").strip().lower()
    if raw == "fast":
        return {"name": "fast", "temperature": 0.2, "max_tokens": 280}
    if raw == "deep":
        return {"name": "deep", "temperature": 0.6, "max_tokens": 900}
    return {"name": "balanced", "temperature": 0.35, "max_tokens": 520}


def _resolve_model_for_profile(model: str | None, profile_name: str) -> str:
    """
    Om explicit modell saknas kan profil välja via env:
      NOUSE_COMPANION_MODEL_FAST / _BALANCED / _DEEP
      fallback till NOUSE_COMPANION_MODEL / default.
    """
    if model and model.strip():
        return model.strip()
    key = f"NOUSE_COMPANION_MODEL_{profile_name.upper()}"
    env_by_profile = os.getenv(key, "").strip()
    if env_by_profile:
        return env_by_profile
    return _resolve_model(None)


def _build_chat_kwargs(
    *,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> dict:
    """
    Bygg provider-korrekta kwargs:
    - Ollama: temperatur/limit via options
    - openai_compatible: standardfält
    """
    provider = os.getenv("NOUSE_LLM_PROVIDER", "ollama").strip().lower()
    if provider == "openai_compatible":
        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    return {
        "model": model,
        "messages": messages,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }


async def companion_loop(
    topic: str | None = None,
    model: str | None = None,
    profile: str | None = None,
) -> None:
    client = AsyncOllama()
    p = _resolve_profile(profile)
    profile_name = str(p["name"])
    chat_model = _resolve_model_for_profile(model, profile_name)
    temperature = float(p["temperature"])
    max_tokens = int(p["max_tokens"])
    messages: list[dict] = [{"role": "system", "content": _build_system_prompt()}]
    turns: list[tuple[str, str]] = []
    topic = (topic or "").strip()

    if topic:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Samtalsfokus för denna session:\n"
                    f"{topic}\n\n"
                    "Starta med en kort gemensam målbild och 3 möjliga nästa steg."
                ),
            }
        )

    console.print(
        Panel(
            "[bold cyan]nouse companion[/bold cyan]\n"
            "Läge för idéutbyte, reflektion och gemensam utveckling.\n"
            + (f"[dim]Topic: {topic}[/dim]\n" if topic else "")
            + f"[dim]Model: {chat_model}[/dim]\n"
            + f"[dim]Profile: {profile_name} · temp={temperature} · max_tokens={max_tokens}[/dim]\n"
            + "[dim]/exit avslutar · /save sparar session[/dim]",
            border_style="cyan",
        )
    )

    if topic:
        topic_trace_id = new_trace_id("companion_topic")
        topic_started = time.monotonic()
        try:
            record_event(
                topic_trace_id,
                "companion.request",
                endpoint="cli.companion",
                model=chat_model,
                payload={
                    "query": f"[topic] {topic}",
                    "attack_plan": build_attack_plan(topic),
                    "profile": profile_name,
                },
            )
            record_event(
                topic_trace_id,
                "companion.llm_call",
                endpoint="cli.companion",
                model=chat_model,
                payload={"messages": len(messages)},
            )
            resp = await client.chat.completions.create(
                **_build_chat_kwargs(
                    model=chat_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
            opening = resp.message.content or ""
            if opening:
                console.print(f"[bold blue]nouse[/bold blue]> {opening}")
                messages.append({"role": "assistant", "content": opening})
                turns.append((f"[topic] {topic}", opening))
                record_event(
                    topic_trace_id,
                    "companion.response",
                    endpoint="cli.companion",
                    model=chat_model,
                    payload={
                        "response": opening,
                        "assumptions": derive_assumptions(opening),
                        "elapsed_ms": int((time.monotonic() - topic_started) * 1000),
                    },
                )
                console.print(f"[dim]trace_id: {topic_trace_id}[/dim]")
                _ingest_exchange(f"[topic] {topic}", opening, trace_id=topic_trace_id)
        except Exception as e:
            console.print(f"[red]Kunde inte starta topic-öppning:[/red] {e}")
            record_event(
                topic_trace_id,
                "companion.error",
                endpoint="cli.companion",
                model=chat_model,
                payload={"error": str(e), "elapsed_ms": int((time.monotonic() - topic_started) * 1000)},
            )

    while True:
        try:
            user_input = input("\nBjörn> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input.lower() in ("/exit", "exit", "quit", "/quit"):
            break
        if user_input.lower() == "/save":
            p = _write_session_log(turns)
            console.print(f"[green]Session sparad:[/green] {p}")
            continue

        trace_id = new_trace_id("companion")
        started = time.monotonic()
        record_event(
            trace_id,
            "companion.request",
            endpoint="cli.companion",
            model=chat_model,
            payload={
                "query": user_input,
                "attack_plan": build_attack_plan(user_input),
                "profile": profile_name,
            },
        )
        messages.append({"role": "user", "content": user_input})
        try:
            record_event(
                trace_id,
                "companion.llm_call",
                endpoint="cli.companion",
                model=chat_model,
                payload={"messages": len(messages)},
            )
            resp = await client.chat.completions.create(
                **_build_chat_kwargs(
                    model=chat_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
            reply = resp.message.content or ""
        except Exception as e:
            console.print(f"[red]Fel:[/red] {e}")
            record_event(
                trace_id,
                "companion.error",
                endpoint="cli.companion",
                model=chat_model,
                payload={"error": str(e), "elapsed_ms": int((time.monotonic() - started) * 1000)},
            )
            messages.pop()
            continue

        console.print(f"[bold blue]nouse[/bold blue]> {reply}")
        console.print(f"[dim]trace_id: {trace_id}[/dim]")
        messages.append({"role": "assistant", "content": reply})
        turns.append((user_input, reply))
        record_event(
            trace_id,
            "companion.response",
            endpoint="cli.companion",
            model=chat_model,
            payload={
                "response": reply,
                "assumptions": derive_assumptions(reply),
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            },
        )
        _ingest_exchange(user_input, reply, trace_id=trace_id)

    if turns:
        p = _write_session_log(turns)
        console.print(f"\n[dim]Session avslutad och sparad:[/dim] {p}")


def run(
    topic: str | None = None,
    model: str | None = None,
    profile: str | None = None,
) -> None:
    asyncio.run(companion_loop(topic=topic, model=model, profile=profile))
