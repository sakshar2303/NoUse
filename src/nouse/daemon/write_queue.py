"""
WriteQueue — Serialiserad skriv-kö
===================================

Alla skrivande API-anrop går via denna kö så att de serialiseras
och inte konkurrerar om SQLite WAL-skrivlåset.

Arkitektur:
  - En global asyncio.Queue med (coroutine, Future)-par
  - En worker-task (körs i daemon event-loop) bearbetar en i taget
  - API-handlers anropar enqueue_write() och awaitar resultatet

Exempel:
    result = await enqueue_write(my_write_coroutine(field, data))

Köns worker startas automatiskt i write_queue_lifespan() — anropas
från server.py:s lifespan-context.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, TypeVar

_log = logging.getLogger("nouse.write_queue")

T = TypeVar("T")

# Global kö — (coroutine, Future, enqueue_time)
_queue: asyncio.Queue[tuple[Awaitable[Any], asyncio.Future[Any], float]] = asyncio.Queue()
_worker_task: asyncio.Task | None = None

# Statistik
_stats = {
    "enqueued":   0,
    "completed":  0,
    "failed":     0,
    "max_wait_s": 0.0,
    "max_run_s":  0.0,
}


async def enqueue_write(coro: Awaitable[T], *, timeout: float = 120.0) -> T:
    """
    Kö upp en skriv-coroutine och returnera resultatet när den är klar.
    Kastar TimeoutError om den väntar längre än `timeout` sekunder.
    """
    loop   = asyncio.get_running_loop()
    future: asyncio.Future[T] = loop.create_future()
    enqueue_time = time.monotonic()

    await _queue.put((coro, future, enqueue_time))
    _stats["enqueued"] += 1

    try:
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
    except asyncio.TimeoutError:
        _log.warning("WriteQueue: timeout efter %.0fs — jobbet körs fortfarande", timeout)
        raise TimeoutError(
            f"Skriv-jobbet väntade mer än {timeout}s i kön. "
            "Systemet är troligen hårt belastat — försök igen."
        )


async def _worker() -> None:
    """
    Kör ett skriv-jobb i taget. Körs som bakgrundsuppgift i event-loopen.
    """
    _log.info("WriteQueue worker startad")
    while True:
        try:
            coro, future, enqueue_time = await _queue.get()
        except asyncio.CancelledError:
            _log.info("WriteQueue worker stoppad")
            return

        wait_s = time.monotonic() - enqueue_time
        _stats["max_wait_s"] = max(_stats["max_wait_s"], wait_s)
        if wait_s > 5.0:
            _log.warning("WriteQueue: jobb väntade %.1fs i kön", wait_s)

        t0 = time.monotonic()
        try:
            result = await coro
            if not future.done():
                future.set_result(result)
            _stats["completed"] += 1
        except Exception as e:
            if not future.done():
                future.set_exception(e)
            _stats["failed"] += 1
            _log.warning("WriteQueue: jobb misslyckades: %s", e)
        finally:
            run_s = time.monotonic() - t0
            _stats["max_run_s"] = max(_stats["max_run_s"], run_s)
            _queue.task_done()


def start_worker() -> None:
    """Starta worker-task i körande event-loop. Anropas vid server-start."""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker(), name="write_queue_worker")
        _log.info("WriteQueue worker task skapad")


def stop_worker() -> None:
    """Stoppa worker-task. Anropas vid server-shutdown."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        _worker_task = None


def queue_stats() -> dict:
    return {
        "queue_depth": _queue.qsize(),
        **_stats,
    }
