"""
FileLock — förhindrar race conditions mellan brain-loop och chat
================================================================
Enkel fcntl-baserad lås. Både brain-loopen och chat-sessioner
skaffar låset innan de skriver till grafen.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

_LOCK_PATH = Path.home() / ".local" / "share" / "b76" / "brain.lock"


class BrainLock:
    """Context manager som håller ett exklusivt filbaserat lås."""

    def __init__(self, path: Path | None = None, timeout: float = 10.0):
        self._path    = path or _LOCK_PATH
        self._timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> "BrainLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR)
        import time
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(self._fd)
                    raise TimeoutError(
                        f"Kunde inte skaffa brain-lås inom {self._timeout}s. "
                        "Brain-loopen kanske kör — försök igen om en stund."
                    )
                time.sleep(0.2)

    def __exit__(self, *_) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
