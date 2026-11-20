"""Look-layer errors. Reuses the CLI's error contract so hints print for free."""
from __future__ import annotations

from deskmark.errors import DeskmarkError


class LookError(DeskmarkError):
    """Something could not be seen or explained."""
