"""
nouse.field.events — Trådsäker event-buss för realtidsvisualisering
=====================================================================

Extremt tunn modul — inga tunga beroenden. Kan importeras från
var som helst (sync eller async) utan cirkulära importproblem.

Användning:
    from nouse.field.events import emit

    emit("edge_added", src="plasticity", tgt="mycel", rel="oscillerar_med",
         evidence_score=0.71, domain_src="neurovetenskap", domain_tgt="biologi")

SSE-endpoint i server.py tömmer kön med drain() och strömmar till browsern.
"""
from __future__ import annotations

import queue
import time
from typing import Any

# Global trådsäker kö — producenter skriver hit, SSE-endpoint läser
_BUS: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()

# Max antal händelser i kön (om ingen lyssnare tömt den)
_MAX_QUEUE = 2000


def emit(event_type: str, **data: Any) -> None:
    """Publicera en händelse på bussen. Icke-blockerande."""
    # Skjut ut gamla events om kön fullnat (ingen lyssnare ansluten)
    # Ingen exakt limit på SimpleQueue, men vi trimmar vid drain.
    _BUS.put_nowait({
        "type": event_type,
        "ts": round(time.time() * 1000),  # millisekunder sedan epoch
        **data,
    })


def drain(max_events: int = 100) -> list[dict[str, Any]]:
    """
    Töm kön och returnera alla väntande händelser.
    Anropas periodiskt av SSE-endpointen.
    """
    events: list[dict[str, Any]] = []
    while len(events) < max_events:
        try:
            events.append(_BUS.get_nowait())
        except queue.Empty:
            break

    # Om kön fortfarande är stor (ingen konsument) — kasta gamla events
    overflow: list[dict[str, Any]] = []
    while True:
        try:
            overflow.append(_BUS.get_nowait())
        except queue.Empty:
            break
    if len(overflow) > _MAX_QUEUE:
        overflow = overflow[-_MAX_QUEUE:]
    for e in overflow:
        _BUS.put_nowait(e)

    return events
