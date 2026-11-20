"""Errors a user or an agent is allowed to see.

No raw OSError or JSONDecodeError should reach a caller. Each error carries a
message and, when there is one, a hint that says what to do about it.
"""
from __future__ import annotations


class DeskmarkError(Exception):
    """Base class for everything this package raises deliberately."""

    def __init__(self, message: str, hint: str = "") -> None:
        self.message = message
        self.hint = hint
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.message}" + (f"\n  hint: {self.hint}" if self.hint else "")


class AmbiguousReference(DeskmarkError):
    """A reference matched more than one point. Refused, never resolved by
    picking one: restoring the wrong desk costs more than an error."""


class StoreError(DeskmarkError):
    """The store could not be read or written."""


class CorruptPointError(StoreError):
    """A resume point file exists but is not parseable."""


class PointNotFound(StoreError):
    """No resume point matches the given reference."""


class CaptureError(DeskmarkError):
    """A capture could not be produced at all (providers failing is *not* this)."""
