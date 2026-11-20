"""Renders a point as text an agent can read.

Bounded by a character budget and ordered by usefulness. It says what is
missing and what is stale, because an agent that can't tell fresh from stale
will happily continue work that no longer exists.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from deskmark.schema import ResumePoint

DEFAULT_BUDGET_CHARS = 4000


def human_age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _repo_block(point: ResumePoint) -> str:
    repo = point.repo
    if not repo:
        return "No git repository was in flight."
    lines = [
        f"repo    {repo.name}  ({repo.root})",
        f"branch  {repo.branch or 'detached'}" + (f"  head {repo.head}" if repo.head else ""),
    ]
    if repo.ahead or repo.behind:
        lines.append(f"sync    {repo.ahead} ahead, {repo.behind} behind upstream")
    if repo.is_clean:
        lines.append("state   clean working tree")
    else:
        bits = []
        if repo.dirty:
            bits.append(f"{len(repo.dirty)} modified")
        if repo.staged:
            bits.append(f"{len(repo.staged)} staged")
        if repo.untracked:
            bits.append(f"{len(repo.untracked)} untracked")
        lines.append("state   " + ", ".join(bits) + (f"  ({repo.diffstat})" if repo.diffstat else ""))
    return "\n".join(lines)


def _files_block(point: ResumePoint, limit: int = 12) -> str:
    files = [f for f in point.files if f.kind == "file"]
    folders = [f for f in point.files if f.kind == "folder"]
    lines: List[str] = []
    if files:
        lines.append("files in flight")
        for ref in files[:limit]:
            lines.append(f"  - {ref.path}  ({ref.reason})")
        if len(files) > limit:
            lines.append(f"  - … {len(files) - limit} more")
    if folders:
        lines.append("roots")
        for ref in folders[:4]:
            lines.append(f"  - {ref.path}  ({ref.reason})")
    return "\n".join(lines)


def _tabs_block(point: ResumePoint, limit: int = 10) -> str:
    if not point.tabs:
        return ""
    grouped: Dict[str, List[str]] = {}
    for tab in point.tabs:
        grouped.setdefault(tab.category, []).append(f"{tab.title}  {tab.url}")
    lines = ["was reading"]
    for category, items in grouped.items():
        for item in items[:limit]:
            lines.append(f"  [{category}] {item}")
    return "\n".join(lines[: limit + 1])


def _terminals_block(point: ResumePoint) -> str:
    if not point.terminals:
        return ""
    lines = ["shells"]
    for term in point.terminals:
        detail = term.last_command or "(no command recorded)"
        tail = f"  (exit {term.exit_code})" if term.exit_code not in (None, 0) else ""
        lines.append(f"  {term.cwd}  last: `{detail}`{tail}")
        if term.last_failure and term.last_failure != term.last_command:
            lines.append(f"    last failure: `{term.last_failure}` (exit {term.last_failure_exit})")
    return "\n".join(lines)


def _agents_block(point: ResumePoint) -> str:
    if not point.agents:
        return ""
    lines = ["agents that were running"]
    for agent in point.agents:
        hint = f"  resume with `{agent.resume_hint}`" if agent.resume_hint else ""
        lines.append(f"  {agent.kind} in {agent.cwd or '?'}{hint}")
    return "\n".join(lines)


def _intent_block(point: ResumePoint) -> str:
    intent = point.intent
    lines = []
    if intent.why:
        lines.append(f"why     {intent.why}" + (f"   [from {intent.why_source}]" if intent.why_source else ""))
    if intent.next_step:
        lines.append(f"next    {intent.next_step}" + (f"   [from {intent.next_source}]" if intent.next_source else ""))
    if intent.note and intent.note != intent.why:
        lines.append(f"note    {intent.note}")
    return "\n".join(lines) if lines else "No explicit intent was recorded. Ask the user what this work was for."


def _questions_block(point: ResumePoint) -> str:
    remaining = [q for q in point.intent.open_questions if q != point.intent.next_step]
    if not remaining:
        return ""
    lines = ["open markers"]
    for question in remaining[:4]:
        lines.append(f"  - {question}")
    return "\n".join(lines)


def render(point: ResumePoint, budget_chars: int = DEFAULT_BUDGET_CHARS,
           now: Optional[float] = None) -> str:
    """Render a context packet within ``budget_chars``, dropping the least useful parts first."""
    now = now or time.time()
    age = human_age(point.age_seconds(now))
    if point.created_at - now > 60:
        staleness = "timestamp is in the future, check the clock"
    elif point.is_stale(now):
        staleness = "STALE, verify before continuing"
    else:
        staleness = "fresh"

    header = (
        f"<!-- deskmark/v1 id={point.id} name={point.name!r} -->\n"
        f"# Resume point: {point.name}\n"
        f"captured {age} · {staleness} · {point.size_bytes()} bytes · zero pixels captured\n"
    )

    sections: List[Tuple[int, str]] = [
        (0, "## Where you were\n" + _repo_block(point)),
        (1, "## Why / next\n" + _intent_block(point)),
        (2, _files_block(point)),
        (3, _agents_block(point)),
        (4, _terminals_block(point)),
        (5, _tabs_block(point)),
        (6, _questions_block(point)),
    ]

    body = header
    omitted: List[str] = []
    for _, section in sections:
        if not section.strip():
            continue
        candidate = body + "\n" + section + "\n"
        if len(candidate) > budget_chars:
            omitted.append(section.splitlines()[0].lstrip("# ").strip())
            continue
        body = candidate

    footer = ""
    if point.provenance:
        sources = sorted({p.get("source", "?") for p in point.provenance.values()})
        footer += f"\nsources: {', '.join(sources)}"
    gaps = [k for k in ("repo", "tabs", "terminals", "agents") if k not in point.provenance]
    if gaps:
        footer += f"\nnot captured: {', '.join(gaps)} (no provider available on this host)"
    if omitted:
        footer += f"\nomitted for budget: {', '.join(omitted)}"
    footer += "\nrestoring reopens the workspace; recorded commands are shown, never executed.\n"

    return (body + footer)[: max(budget_chars, len(header)) + 400]


def render_json(point: ResumePoint, budget_chars: int = 0) -> str:
    """Machine-first rendering. ``budget_chars`` 0 means no truncation."""
    data: Dict[str, Any] = {
        "schema": point.schema,
        "id": point.id,
        "name": point.name,
        "age_seconds": int(point.age_seconds()),
        "stale": point.is_stale(),
        "intent": point.intent.to_dict(),
        "repo": point.repo.to_dict() if point.repo else None,
        "files": [{"path": f.path, "kind": f.kind, "reason": f.reason} for f in point.files],
        "tabs": [t.to_dict() for t in point.tabs],
        "terminals": [t.to_dict() for t in point.terminals],
        "agents": [a.to_dict() for a in point.agents],
        "provenance": point.provenance,
    }
    text = json.dumps(data, indent=2)
    return text[:budget_chars] if budget_chars else text
