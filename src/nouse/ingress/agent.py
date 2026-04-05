"""
nouse.ingress.agent — Generisk agent-ingress
=============================================
Renommerad och generaliserad version av clawbot-ingressen.
Tar emot text-events från vilken extern agent som helst
(Telegram, CLI-agenter, webhook-triggers, etc.)

Bakåtkompatibilitet: clawbot.py-funktionerna finns kvar och
delegerar hit. Ny kod bör använda dessa namn.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from nouse.ingress.clawbot import (
    ingest_clawbot_event as _ingest,
    approve_clawbot_pairing as _approve,
    get_clawbot_allowlist as _allowlist,
)
from nouse.ingress.allowlist import INGRESS_ALLOWLIST_PATH


def ingest_agent_event(
    *,
    text: str,
    channel: str = "default",
    actor_id: str = "",
    source: str = "agent",
    mode: str = "now",
    strict_pairing: bool = True,
    context_key: str = "",
    allowlist_path: Path = INGRESS_ALLOWLIST_PATH,
) -> dict[str, Any]:
    """Lägg till ett text-event från en extern agent i Nouse ingress-kön."""
    return _ingest(
        text=text,
        channel=channel,
        actor_id=actor_id,
        source=source,
        mode=mode,
        strict_pairing=strict_pairing,
        context_key=context_key,
        allowlist_path=allowlist_path,
    )


def approve_agent_pairing(
    channel: str,
    code: str,
    *,
    path: Path = INGRESS_ALLOWLIST_PATH,
) -> dict[str, Any] | None:
    """Godkänn en väntande pairing-förfrågan från en extern agent."""
    return _approve(channel, code, path=path)


def get_agent_allowlist(
    channel: str,
    *,
    path: Path = INGRESS_ALLOWLIST_PATH,
) -> dict[str, Any]:
    """Hämta allowlist-status för en given kanal."""
    return _allowlist(channel, path=path)
