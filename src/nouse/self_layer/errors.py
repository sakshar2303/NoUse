from __future__ import annotations


class SelfLayerError(Exception):
    """Basfel för self-layer operationer."""


class IdentityProfileError(SelfLayerError):
    """Fel kopplat till persistent identity-profile."""


class SelfMemoryError(SelfLayerError):
    """Fel kopplat till lagring/läsning av self-minnen."""
