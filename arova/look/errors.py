"""Look-layer errors. Reuses the CLI's error contract so hints print for free."""
from __future__ import annotations

from arova.resume.errors import ResumeError


class LookError(ResumeError):
    """Something could not be seen or explained."""
