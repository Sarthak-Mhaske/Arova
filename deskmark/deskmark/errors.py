"""Errors that a user or an agent is allowed to see.

The rule: no raw ``OSError`` or ``JSONDecodeError`` ever escapes to a caller.
Every failure says what happened, where, and what to do about it — because the
caller is either a human in a terminal or an agent that will otherwise report
"something went wrong" to that human.
"""
from __future__ import annotations


class ResumeError(Exception):
    """Base class for everything this package raises deliberately."""

    def __init__(self, message: str, hint: str = "") -> None:
        self.message = message
        self.hint = hint
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.message}" + (f"\n  hint: {self.hint}" if self.hint else "")


class StoreError(ResumeError):
    """The store could not be read or written."""


class CorruptPointError(StoreError):
    """A resume point file exists but is not parseable."""


class PointNotFound(StoreError):
    """No resume point matches the given reference."""


class CaptureError(ResumeError):
    """A capture could not be produced at all (providers failing is *not* this)."""
