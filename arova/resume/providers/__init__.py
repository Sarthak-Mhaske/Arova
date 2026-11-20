"""Capture providers.

Each provider answers one question about work in flight and reports how sure
it is. Providers never raise into the caller: a missing browser, an odd git
state, or a locked database degrades to "not captured", never to a crash.

That rule is why Arova can claim "it never breaks your day": there is no
capture path that can take the tool down with it.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_HOURS = 12.0


def run(cmd: List[str], cwd: Optional[str] = None, timeout: float = 5.0) -> Tuple[int, str]:
    """Run a short subprocess and never raise. Returns (returncode, stdout)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return proc.returncode, (proc.stdout or "")
    except Exception as exc:  # missing binary, timeout, permission
        logger.debug("command failed %s: %s", cmd, exc)
        return 1, ""


def file_mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


class Collector:
    """Accumulates sections plus their provenance, tolerating per-section failure."""

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.provenance: Dict[str, Dict[str, Any]] = {}
        self.redactions: List[str] = []
        self.warnings: List[str] = []

    def add(self, key: str, value: Any, source: str, method: str,
            confidence: float = 1.0, ttl_seconds: int = 86400) -> None:
        self.data[key] = value
        self.provenance[key] = {
            "source": source,
            "method": method,
            "confidence": confidence,
            "captured_at": time.time(),
            "ttl_seconds": ttl_seconds,
        }

    def skip(self, key: str, reason: str) -> None:
        self.warnings.append(f"{key}: {reason}")

    def redact(self, description: str) -> None:
        self.redactions.append(description)

