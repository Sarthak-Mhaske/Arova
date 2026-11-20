"""One screenshot, one question, on demand.

There is no capture loop here. You ask, it takes one shot, sends it to the
provider you configured, prints the answer and forgets it. No tool and no key
are both just errors with a hint.
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
