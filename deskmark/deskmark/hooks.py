"""Opt-in shell hooks.

Without a hook Deskmark still works: it can see live shells and git state. With
the hook it also knows what last failed in which directory, which is what makes
the "next step" line useful.

Installing is one marked block in your rc file; uninstalling removes exactly
that block and nothing else.
"""
from __future__ import annotations

import os
import shutil
from typing import List

from .store import deskmark_home

BLOCK_START = "# >>> deskmark shell hook >>>"
BLOCK_END = "# <<< deskmark shell hook <<<"


def hook_dest() -> str:
    """The installed hook follows DESKMARK_HOME, like the points and the log."""
    return os.path.join(deskmark_home(), "shell_hook.sh")


def _source_hook() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks", "shell_hook.sh")


def rc_files() -> List[str]:
    home = os.path.expanduser("~")
    candidates = [os.path.join(home, ".zshrc"), os.path.join(home, ".bashrc")]
    return [path for path in candidates if os.path.exists(path)]


def install(dry_run: bool = False) -> List[str]:
    actions: List[str] = []
    source = _source_hook()
    if not os.path.exists(source):
        return [f"hook script missing at {source}"]

    if not dry_run:
        os.makedirs(os.path.dirname(hook_dest()), exist_ok=True)
        shutil.copyfile(source, hook_dest())
    actions.append(f"{'would copy' if dry_run else 'copied'} hook to {hook_dest()}")

    block = f"{BLOCK_START}\n[ -f \"{hook_dest()}\" ] && source \"{hook_dest()}\"\n{BLOCK_END}\n"
    for rc in rc_files():
        try:
            with open(rc, "r", encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        if BLOCK_START in content:
            actions.append(f"{rc} already hooked")
            continue
        if not dry_run:
            with open(rc, "a", encoding="utf-8") as handle:
                handle.write("\n" + block)
        actions.append(f"{'would add' if dry_run else 'added'} hook to {rc}")
    return actions


def uninstall(dry_run: bool = False) -> List[str]:
    actions: List[str] = []
    for rc in rc_files():
        try:
            with open(rc, "r", encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        if BLOCK_START not in content:
            continue
        start = content.index(BLOCK_START)
        end = content.find(BLOCK_END, start)
        end = end + len(BLOCK_END) if end != -1 else len(content)
        cleaned = (content[:start] + content[end:]).rstrip() + "\n"
        if not dry_run:
            with open(rc, "w", encoding="utf-8") as handle:
                handle.write(cleaned)
        actions.append(f"{'would remove' if dry_run else 'removed'} hook from {rc}")
    if os.path.exists(hook_dest()):
        if not dry_run:
            os.unlink(hook_dest())
        actions.append(f"{'would delete' if dry_run else 'deleted'} {hook_dest()}")
    return actions or ["no hook installed"]
