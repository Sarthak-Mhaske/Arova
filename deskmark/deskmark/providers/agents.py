"""Coding agents that were running when the point was taken.

We record which agent, where it ran, and the session id needed to continue. We
never call the agent's API and never read the conversation.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from deskmark.schema import AgentRef

# what an agent's executable is called. matching is on argv[0], not on the
# whole command line: a regex over the line classified "python3 serve.py
# ~/claude-notes/x.md" as a claude session, which is the kind of false positive
# that makes the whole section untrustworthy.
AGENT_EXECUTABLES: Dict[str, str] = {
    "claude": "claude",
    "codex": "codex",
    "cursor-agent": "cursor",
    "opencode": "opencode",
    "openclaw": "openclaw",
    "clawdbot": "openclaw",
    "moltbot": "openclaw",
    "aider": "aider",
    "aider-chat": "aider",
    "gemini": "gemini",
    "goose": "goose",
    "amp": "amp",
}

# agents that ship as a package get started through a runtime, e.g.
# node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js. these directory
# names are specific enough that a project folder won't collide with them.
AGENT_PACKAGES: Dict[str, str] = {
    "claude-code": "claude",
    "codex-cli": "codex",
    "cursor-agent": "cursor",
    "opencode-ai": "opencode",
    "aider-chat": "aider",
    "gemini-cli": "gemini",
    "goose-cli": "goose",
}

# a script run by one of these is an agent if its argument is
INTERPRETERS = frozenset({
    "node", "bun", "deno", "npx", "pnpm", "yarn", "uv", "uvx", "pipx", "sh", "bash", "zsh",
})

# session ids are uuids in practice. "claude --resume import" came out of a
# python -c "...import time..." being read as a --continue flag.
SESSION_FLAGS = ("--resume", "--session", "--session-id", "--continue")
_SESSION_ID = re.compile(
    r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9A-Za-z_-]{16,64})$"
)


def _cmdline(pid: str) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            raw = handle.read()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "ignore").strip()


def _classify(cmdline: str) -> Optional[str]:
    """Which agent this process is, decided on the program it was started as."""
    parts = cmdline.split()
    if not parts:
        return None

    program = os.path.basename(parts[0]).lower()
    kind = AGENT_EXECUTABLES.get(program)
    if kind:
        return kind

    is_interpreter = program in INTERPRETERS or program.startswith("python")
    if not is_interpreter:
        return None

    # only the arguments that point at what is being run, not every string on
    # the line: a path four arguments in is a path, not a program
    arguments = parts[1:4]
    for argument in arguments:
        if argument == "-m":                      # python3 -m aider
            continue
        base = os.path.basename(argument).lower()
        if base in AGENT_EXECUTABLES:
            return AGENT_EXECUTABLES[base]
        for segment in argument.lower().split("/"):
            if segment in AGENT_PACKAGES:
                return AGENT_PACKAGES[segment]

    if "-m" in arguments:
        index = arguments.index("-m")
        if index + 1 < len(arguments):
            module = arguments[index + 1].split(".")[0].lower()
            if module in AGENT_EXECUTABLES:
                return AGENT_EXECUTABLES[module]
    return None


def _session_from_cmdline(cmdline: str) -> str:
    """The session id, if a long flag carried one.

    Short flags are not looked at: -c is --continue here, compile-and-run in
    python, and a git option, and guessing produced resume commands that run
    something else entirely.
    """
    parts = cmdline.split()
    for index, token in enumerate(parts):
        for flag in SESSION_FLAGS:
            if token == flag and index + 1 < len(parts):
                candidate = parts[index + 1].strip()
                if _SESSION_ID.match(candidate):
                    return candidate
            if token.startswith(flag + "="):
                candidate = token.split("=", 1)[1].strip()
                if _SESSION_ID.match(candidate):
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
    # linux only for now: /proc is the whole implementation. macos and windows
    # get no agent section rather than a wrong one.
    if not os.path.isdir("/proc"):
        return []

    found: Dict[Tuple[str, str], AgentRef] = {}
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return []

    for pid in pids:
        if pid == str(os.getpid()):
            continue
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

        # /proc reports a deleted cwd as "/path (deleted)". There is nothing to
        # resume there, so skip it instead of offering a broken hint.
        if cwd.endswith(" (deleted)"):
            continue
        # no readable cwd means another user's process, which we can see but
        # cannot say anything useful about
        if not cwd:
            continue

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
