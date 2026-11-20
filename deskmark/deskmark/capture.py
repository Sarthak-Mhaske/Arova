"""Builds one resume point from whatever this machine can tell us.

Budgeted to a few KB and well under a second. A provider that is missing, slow
or broken adds a warning and leaves a gap in provenance; the point is still
written.
"""
from __future__ import annotations

import os
from typing import List, Optional

from deskmark import providers
from deskmark.intent import derive
from deskmark.providers.agents import capture_agents
from deskmark.providers.repo import capture_repo, open_questions, working_set_files
from deskmark.providers.sessions import open_tabs
from deskmark.providers.terminal import capture_from_log, capture_live_shells, merge
from deskmark.schema import (
    AgentRef,
    FileRef,
    ResumePoint,
    TabRef,
    TerminalRef,
    local_host_info,
)

DEFAULT_WINDOW_HOURS = 12.0
MAX_TABS = 12
MAX_TERMINALS = 6
MAX_AGENTS = 6


class CaptureResult:
    def __init__(self, point: ResumePoint, warnings: List[str]):
        self.point = point
        self.warnings = warnings


def capture(
    name: str,
    cwd: Optional[str] = None,
    note: str = "",
    why: str = "",
    next_step: str = "",
    window_hours: float = DEFAULT_WINDOW_HOURS,
    browser: bool = True,
    agents: bool = True,
    ttl_seconds: int = 7 * 24 * 3600,
) -> CaptureResult:
    cwd = os.path.abspath(cwd or os.getcwd())
    collector = providers.Collector()

    repo_redactions: List[str] = []
    repo = capture_repo(cwd, redactions=repo_redactions)
    for redaction in repo_redactions:
        collector.redact(redaction)

    files: List[FileRef] = []
    questions: List[str] = []
    if repo:
        collector.add("repo", repo.to_dict(), "git",
                      "rev-parse + status --porcelain + log", confidence=1.0, ttl_seconds=3600)
        files = working_set_files(repo)
        questions = open_questions(repo)
        collector.add("open_questions", questions, "git", "TODO scan of working set",
                      confidence=0.7, ttl_seconds=7 * 86400)
    else:
        collector.skip("repo", "not inside a git repository")

    terminals: List[TerminalRef] = []
    try:
        log_terminals = capture_from_log(window_hours=window_hours)
        live_terminals = capture_live_shells()
        terminals = merge(log_terminals, live_terminals, limit=MAX_TERMINALS)
        if terminals:
            collector.add("terminals", [t.to_dict() for t in terminals], "shell-hook+proc",
                          "session_log.jsonl + /proc/<pid>/cwd", confidence=0.9, ttl_seconds=6 * 3600)
        else:
            collector.skip("terminals", "no shell hook log and no live shells found")
    except Exception as exc:  # pragma: no cover - defensive
        collector.skip("terminals", str(exc))

    # repo root first, that is where a restore starts
    seen_paths = {f.path.rstrip("/") for f in files}
    if repo and os.path.isdir(repo.root):
        files = [f for f in files if f.path.rstrip("/") != repo.root.rstrip("/")]
        files.insert(0, FileRef(path=repo.root, kind="folder", reason="repo-root"))
        seen_paths.add(repo.root.rstrip("/"))

    # shell cwds belong in the working set too
    for term in terminals:
        key = (term.cwd or "").rstrip("/")
        if key and key not in seen_paths and os.path.isdir(term.cwd):
            files.append(FileRef(path=term.cwd, kind="folder", reason="terminal-cwd"))
            seen_paths.add(key)

    tabs: List[TabRef] = []
    if browser:
        try:
            captured, redactions, profiles = open_tabs(limit=MAX_TABS)
            for redaction in redactions:
                collector.redact(redaction)
            if captured is None:
                collector.skip("tabs", "no supported browser profile found")
            elif not captured:
                collector.skip("tabs", f"{profiles} browser profile(s) found, nothing open")
            else:
                tabs = captured
                collector.add("tabs", [t.to_dict() for t in tabs], "browser-session",
                              "read-only parse of the browser session log", confidence=0.9,
                              ttl_seconds=6 * 3600)
        except Exception as exc:  # pragma: no cover - defensive
            collector.skip("tabs", str(exc))

    agent_refs: List[AgentRef] = []
    if agents:
        try:
            agent_refs = capture_agents(limit=MAX_AGENTS)
            if agent_refs:
                collector.add("agents", [a.to_dict() for a in agent_refs], "proc",
                              "/proc cmdline scan + agent session files", confidence=0.85,
                              ttl_seconds=6 * 3600)
        except Exception as exc:  # pragma: no cover - defensive
            collector.skip("agents", str(exc))

    intent = derive(repo, questions, terminals, note=note, why=why, next_step=next_step)

    point = ResumePoint(
        name=name.strip() or "untitled",
        host=local_host_info(),
        repo=repo,
        files=files,
        tabs=tabs,
        terminals=terminals,
        agents=agent_refs,
        intent=intent,
        provenance=collector.provenance,
        redactions=collector.redactions,
        ttl_seconds=ttl_seconds,
    )
    point.digest = point.to_dict()["digest"]
    return CaptureResult(point, collector.warnings)
