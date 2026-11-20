"""Looking at the screen, on purpose, once.

``deskmark look`` answers one question — *what am I looking at, and what does it
mean* — without a daemon, without continuous capture, and without pixels
leaving the machine unless you asked for an answer.

Everything in here is best-effort against whatever the machine actually has:
PIL if it is installed, otherwise the CLI tool the platform ships, otherwise a
clear error that says what to install. Nothing is required.
"""
from __future__ import annotations

from deskmark.look.errors import LookError
from deskmark.look.screen import WindowRef, active_window, available_tools, capture  # noqa: E402
from deskmark.look.understand import DEFAULT_QUESTION, Answer, ask, detect_provider  # noqa: E402

__all__ = [
    "DEFAULT_QUESTION",
    "Answer",
    "LookError",
    "WindowRef",
    "active_window",
    "ask",
    "available_tools",
    "capture",
    "detect_provider",
]
