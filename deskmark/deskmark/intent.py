"""Works out "why" and "next" from what was already captured.

No model, no network, deterministic: same state in, same intent out. Every
answer records where it came from (why_source / next_source), and --why or
--next from the user always wins over anything inferred.
"""
from __future__ import annotations

import os
from typing import List, Optional

from deskmark.schema import Intent, RepoState, TerminalRef

VAGUE_BRANCHES = {"main", "master", "develop", "dev", "trunk"}


def _humanize_branch(branch: str) -> str:
    import re
    parts = branch.split("/")[-1]
    # strip generated ids ("35f69639-", "ARO-142-") so slugs stay readable
    parts = re.sub(r"^[0-9a-f]{6,}-", "", parts)
    parts = re.sub(r"^[A-Z]{2,8}-\d+[-_]", "", parts)
    return parts.replace("-", " ").replace("_", " ").strip()


def derive(repo: Optional[RepoState],
           questions: Optional[List[str]] = None,
           terminals: Optional[List[TerminalRef]] = None,
           note: str = "",
           why: str = "",
           next_step: str = "") -> Intent:
    questions = questions or []
    terminals = terminals or []

    intent = Intent(note=note.strip(), open_questions=list(questions))

    # --- why ---

    if why.strip():
        intent.why, intent.why_source = why.strip(), "user"
    elif note.strip():
        intent.why, intent.why_source = note.strip(), "note"
    elif repo:
        if repo.branch and repo.branch not in VAGUE_BRANCHES:
            intent.why = f"working on “{_humanize_branch(repo.branch)}”"
            intent.why_source = "branch"
        elif repo.recent_commits:
            intent.why = repo.recent_commits[0]["subject"]
            intent.why_source = "commit"
    if repo and repo.diffstat and intent.why and intent.why_source in ("branch", "commit"):
        intent.why = f"{intent.why} ({repo.diffstat})"

    # --- next ---

    if next_step.strip():
        intent.next_step, intent.next_source = next_step.strip(), "user"
    elif questions:
        intent.next_step, intent.next_source = questions[0], "todo"
    else:
        failing = [t for t in terminals if t.last_failure]
        if failing:
            worst = failing[0]
            where = os.path.basename(worst.cwd.rstrip("/")) or worst.cwd
            intent.next_step = (f"last thing that broke in {where}: `{worst.last_failure}` "
                                f"(exit {worst.last_failure_exit})")
            intent.next_source = "terminal-exit"

    return intent
