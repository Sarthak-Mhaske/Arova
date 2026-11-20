"""Errors that a user or an agent is allowed to see.

The rule: no raw ``OSError`` or ``JSONDecodeError`` ever escapes to a caller.
Every failure says what happened, where, and what to do about it — because the
caller is either a human in a terminal or an agent that will otherwise report
"something went wrong" to that human.
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
    """A reference matched more than one resume point. Restoring the wrong desk
    is worse than an error message, so this is never resolved by guessing."""


class StoreError(DeskmarkError):
    """The store could not be read or written."""


class CorruptPointError(StoreError):
    """A resume point file exists but is not parseable."""


class PointNotFound(StoreError):
    """No resume point matches the given reference."""


class CaptureError(DeskmarkError):
    """A capture could not be produced at all (providers failing is *not* this)."""
