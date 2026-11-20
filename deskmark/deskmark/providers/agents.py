"""Coding agents that were running when the point was taken.

In 2026 a working session is rarely just you: it is you plus two or three
agents in different terminals. Those agents hold state that no file records —
the conversation. This provider finds them and, where the agent exposes a
session file on disk, records the id needed to resume the conversation.

Deskmark never talks to the agent's API and never reads the conversation. It
records only: which agent, where, and which session to continue.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from deskmark.schema import AgentRef

AGENT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("claude", re.compile(r"\bclaude\b")),
    ("codex", re.compile(r"\bcodex\b")),
    ("cursor", re.compile(r"cursor-agent|\bcursor\b")),
    ("opencode", re.compile(r"\bopencode\b")),
    ("openclaw", re.compile(r"\bopenclaw\b|\bclawdbot\b|\bmoltbot\b")),
    ("aider", re.compile(r"\baider\b")),
    ("gemini", re.compile(r"\bgemini\b")),
    ("goose", re.compile(r"\bgoose\b")),
    ("amp", re.compile(r"\bamp\b")),
]

# Flags that carry a session identifier the agent can be resumed with.
SESSION_FLAGS = ("--resume", "-r", "--session", "--session-id", "--continue", "-c")


def _cmdline(pid: str) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            raw = handle.read()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "ignore").strip()


def _classify(cmdline: str) -> Optional[str]:
    lowered = cmdline.lower()
    # Do not mistake our own process, a grep, or a shell for an agent.
    if not cmdline or "deskmark" in lowered and "resume" in lowered:
        return None
    if any(token in lowered for token in ("grep", " rg ", "ps aux", "less ", "vim ", "nvim ")):
        return None
    for kind, pattern in AGENT_PATTERNS:
        if pattern.search(lowered):
            return kind
    return None


def _session_from_cmdline(cmdline: str) -> str:
    parts = cmdline.split()
    for index, token in enumerate(parts):
        for flag in SESSION_FLAGS:
            if token == flag and index + 1 < len(parts):
                candidate = parts[index + 1].strip()
                if re.fullmatch(r"[A-Za-z0-9_-]{6,64}", candidate):
                    return candidate
            if token.startswith(flag + "="):
                candidate = token.split("=", 1)[1].strip()
                if re.fullmatch(r"[A-Za-z0-9_-]{6,64}", candidate):
                    return candidate
    return ""


def _claude_session_for(cwd: str) -> Tuple[str, str]:
    """Newest Claude Code session id for this directory, if any."""
    if not cwd:
        return "", ""
    projects = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    slug = cwd.replace("/", "-").replace("\\", "-")
    directory = os.path.join(projects, slug)
    if not os.path.isdir(directory):
        return "", ""
    newest, newest_mtime = "", 0.0
    try:
        for name in os.listdir(directory):
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(directory, name)
            mtime = os.path.getmtime(path)
            if mtime > newest_mtime:
                newest, newest_mtime = os.path.splitext(name)[0], mtime
    except OSError:
        return "", ""
    if not newest:
        return "", ""
    return newest, f"claude --resume {newest}"


def _resume_hint(kind: str, session_id: str, cwd: str) -> str:
    if kind == "claude" and session_id:
        return f"claude --resume {session_id}"
    if kind == "codex" and session_id:
        return f"codex resume {session_id}"
    if kind == "opencode" and session_id:
        return f"opencode --session {session_id}"
    if kind == "cursor":
        return "cursor-agent --resume" if session_id else "cursor-agent"
    return kind


def capture_agents(limit: int = 6) -> List[AgentRef]:
    if not os.path.isdir("/proc"):
        return []

    found: Dict[Tuple[str, str], AgentRef] = {}
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return []

    for pid in pids:
        cmdline = _cmdline(pid)
        if not cmdline:
            continue
        kind = _classify(cmdline)
        if not kind:
            continue
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            cwd = ""

        session_id = _session_from_cmdline(cmdline)
        hint = ""
        if kind == "claude":
            on_disk, disk_hint = _claude_session_for(cwd)
            session_id = session_id or on_disk
            hint = disk_hint or ""
        if not hint:
            hint = _resume_hint(kind, session_id, cwd)

        key = (kind, cwd)
        if key in found:
            continue
        found[key] = AgentRef(
            kind=kind,
            pid=int(pid),
            cwd=cwd,
            session_id=session_id,
            resume_hint=hint,
        )
        if len(found) >= limit:
            break

    return list(found.values())
