"""Git state: root, branch, head, dirty files, TODOs.

The only part of a point that can be checked against reality later.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from deskmark.providers import run
from deskmark.schema import FileRef, RepoState

MAX_FILES = 40
MAX_COMMITS = 5
MAX_TODO_SCAN_BYTES = 64 * 1024
TODO_MARKERS = ("TODO", "FIXME", "XXX", "HACK")


def repo_root(path: str) -> Optional[str]:
    code, out = run(["git", "rev-parse", "--show-toplevel"], cwd=path)
    if code == 0 and out.strip():
        return out.strip()
    return None


def capture_repo(cwd: str) -> Optional[RepoState]:
    root = repo_root(cwd)
    if not root:
        return None

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)[1].strip()
    head = run(["git", "rev-parse", "--short", "HEAD"], cwd=root)[1].strip()
    remote = run(["git", "remote", "get-url", "origin"], cwd=root)[1].strip()

    ahead = behind = 0
    code, counts = run(["git", "rev-list", "--left-right", "--count", "@{u}...HEAD"], cwd=root)
    if code == 0 and counts.strip():
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])

    dirty: List[str] = []
    staged: List[str] = []
    untracked: List[str] = []
    code, porcelain = run(["git", "status", "--porcelain"], cwd=root)
    if code == 0:
        for line in porcelain.splitlines():
            if len(line) < 4:
                continue
            index_status, worktree_status, path = line[0], line[1], line[3:].strip()
            if path.startswith('"') and path.endswith('"'):
                path = path[1:-1]
            if index_status == "?" and worktree_status == "?":
                untracked.append(path)
            elif index_status not in (" ", "?"):
                staged.append(path)
            if worktree_status not in (" ", "?"):
                dirty.append(path)

    commits: List[Dict[str, Any]] = []
    code, log = run(["git", "log", f"-{MAX_COMMITS}", "--pretty=format:%h\x1f%s\x1f%ct"], cwd=root)
    if code == 0:
        for line in log.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 3:
                commits.append({"sha": parts[0], "subject": parts[1], "at": float(parts[2] or 0)})

    diffstat = ""
    code, stat = run(["git", "diff", "--stat"], cwd=root)
    if code == 0 and stat.strip():
        diffstat = stat.strip().splitlines()[-1].strip()

    return RepoState(
        root=root,
        name=os.path.basename(root),
        branch=branch,
        head=head,
        remote=remote,
        ahead=ahead,
        behind=behind,
        dirty=sorted(set(dirty)),
        staged=sorted(set(staged)),
        untracked=sorted(set(untracked)),
        recent_commits=commits,
        diffstat=diffstat,
    )


def working_set_files(repo: RepoState, limit: int = MAX_FILES) -> List[FileRef]:
    """Changed files first, tip-commit files as a fallback for a clean tree.

    Capped hard. A point that lists every file in the repo is noise, and the
    cap is also what keeps capture under a second on a big checkout.
    """
    now = time.time()
    refs: List[FileRef] = []
    seen = set()

    def add(rel: str, reason: str) -> None:
        if rel in seen or len(refs) >= limit:
            return
        seen.add(rel)
        abs_path = rel if os.path.isabs(rel) else os.path.join(repo.root, rel)
        if not os.path.exists(abs_path):
            return
        kind = "folder" if os.path.isdir(abs_path) else "file"
        refs.append(FileRef(path=abs_path, kind=kind, reason=reason, touched_at=now))

    for rel in repo.dirty:
        add(rel, "dirty")
    for rel in repo.staged:
        add(rel, "staged")
    for rel in repo.untracked:
        add(rel, "new")

    # last resort: the tip commit. weaker than a branch or a failing command,
    # so it only gets used when nothing else said anything.
    if not refs:
        code, names = run(["git", "show", "--name-only", "--pretty=format:"], cwd=repo.root)
        if code == 0:
            for rel in names.splitlines()[:10]:
                rel = rel.strip()
                if rel:
                    add(rel, "recent")

    return refs


def open_questions(repo: RepoState, limit: int = 3) -> List[str]:
    """TODO/FIXME markers in the working set.

    Only the head of each file, and only text-ish extensions, so a large binary
    or a minified bundle can't stall capture.
    """
    found: List[str] = []
    candidates = list(dict.fromkeys(repo.dirty + repo.staged))
    for rel in candidates:
        if len(found) >= limit:
            break
        path = rel if os.path.isabs(rel) else os.path.join(repo.root, rel)
        try:
            if not os.path.isfile(path) or os.path.getsize(path) > 4 * 1024 * 1024:
                continue
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                chunk = handle.read(MAX_TODO_SCAN_BYTES)
        except OSError:
            continue
        for line_no, line in enumerate(chunk.splitlines(), start=1):
            stripped = line.strip()
            if any(marker in stripped for marker in TODO_MARKERS):
                text = stripped.lstrip("/#*- ").strip()
                if text and len(text) < 180:
                    found.append(f"{rel}:{line_no}: {text}")
                break
    return found
