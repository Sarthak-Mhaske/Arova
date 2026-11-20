"""Where the shells were, and what last failed there.

Two partial sources: the JSONL log the shell hook writes, and /proc for live
shells. Command text is redacted on read, so a credential in the log doesn't
reach the point.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List, Optional

from deskmark.schema import TerminalRef
from .privacy import redact_command

SECRET_PATTERNS = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|auth[_-]?key|bearer|private[_-]?key)"
    r"\s*[=:]",
    re.IGNORECASE,
)
SHELL_NAMES = {"bash", "zsh", "fish", "sh", "nu", "elvish", "xonsh"}


def log_path() -> str:
    """Where the shell hook writes, and where we read. DESKMARK_HOME wins."""
    home = os.environ.get("DESKMARK_HOME")
    if home:
        return os.path.join(home, "session_log.jsonl")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "deskmark", "session_log.jsonl")


def capture_from_log(window_hours: float = 12.0, limit: int = 8,
                     redactions: Optional[List[str]] = None) -> List[TerminalRef]:
    """Commands and last failures, newest first, credentials stripped.

    ``redactions`` is an out-parameter: pass a list and it gets one summary
    entry, so the point can say it withheld something without saying what.
    """
    leaked = 0
    path = log_path()
    if not os.path.exists(path):
        return []

    cutoff = time.time() - window_hours * 3600
    by_cwd: Dict[str, TerminalRef] = {}
    cwd_by_cmd: Dict[str, str] = {}
    # command text per cmd_id, so an output event is attributed to the command
    # it belongs to instead of to whatever line happened to come before it
    command_by_cmd: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                kind = event.get("type")
                if kind not in ("terminal_command", "terminal_output"):
                    continue
                ts = _parse_ts(event.get("timestamp"))
                if ts and ts < cutoff:
                    continue
                data = event.get("data") or {}
                cmd_id = str(data.get("cmd_id") or "")
                cwd = data.get("cwd") or cwd_by_cmd.get(cmd_id, "")
                if not cwd:
                    continue

                ref = by_cwd.get(cwd) or TerminalRef(cwd=cwd)
                command = data.get("command") or ""
                if command:
                    command, hits = redact_command(command)
                    leaked += hits
                    command = command[:300]
                    ref.last_command = command
                    ref.at = ts or time.time()
                    if cmd_id:
                        command_by_cmd[cmd_id] = command
                if cmd_id:
                    cwd_by_cmd[cmd_id] = cwd

                if kind == "terminal_output":
                    exit_code = data.get("exit_code")
                    if isinstance(exit_code, int):
                        ref.exit_code = exit_code
                        ref.duration_ms = data.get("duration_ms")
                        failed = command or command_by_cmd.get(cmd_id, "")
                        if exit_code != 0 and failed:
                            ref.last_failure = failed
                            ref.last_failure_exit = exit_code
                by_cwd[cwd] = ref
    except OSError:
        return []

    if leaked and redactions is not None:
        redactions.append(f"command text ×{leaked}")

    refs = sorted(by_cwd.values(), key=lambda r: r.at, reverse=True)
    return refs[:limit]


def capture_live_shells(limit: int = 8) -> List[TerminalRef]:
    """Live interactive shells from /proc (Linux only; harmless elsewhere)."""
    if not os.path.isdir("/proc"):
        return []
    uid = os.getuid()
    refs: List[TerminalRef] = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return []
    for pid in pids:
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            comm = open(f"/proc/{pid}/comm", "r").read().strip()
            if comm not in SHELL_NAMES:
                continue
            cwd = os.readlink(f"/proc/{pid}/cwd")
            if not os.access(cwd, os.R_OK):
                continue
            refs.append(TerminalRef(cwd=cwd, shell=comm, pid=int(pid), at=_proc_start(pid)))
        except OSError:
            continue
        if len(refs) >= limit * 2:
            break
    # one entry per cwd, newest shell wins
    seen = {}
    for ref in sorted(refs, key=lambda r: r.at or 0, reverse=True):
        seen.setdefault(ref.cwd, ref)
    return list(seen.values())[:limit]


def _proc_start(pid: str) -> float:
    try:
        with open(f"/proc/{pid}/stat", "r") as handle:
            fields = handle.read().split()
        start_ticks = float(fields[21])
        with open("/proc/uptime", "r") as handle:
            uptime = float(handle.read().split()[0])
        return time.time() - uptime + start_ticks / os.sysconf("SC_CLK_TCK")
    except Exception:
        return time.time()


def _parse_ts(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def merge(log_refs: List[TerminalRef], live_refs: List[TerminalRef], limit: int = 8) -> List[TerminalRef]:
    """Prefer log entries (they carry intent) but keep live cwds with no log."""
    merged: Dict[str, TerminalRef] = {}
    for ref in log_refs:
        merged[ref.cwd] = ref
    for ref in live_refs:
        existing = merged.get(ref.cwd)
        if existing is None:
            merged[ref.cwd] = ref
        elif not existing.shell:
            existing.shell = ref.shell
            existing.pid = ref.pid
    return sorted(merged.values(), key=lambda r: r.at, reverse=True)[:limit]
