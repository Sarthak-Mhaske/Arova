"""Opt-in shell hooks.

Without a hook Arova still works: it can see live shells and git state. With
the hook it also knows what last failed in which directory, which is what makes
the "next step" line useful.

Installing is one marked block in your rc file; uninstalling removes exactly
that block and nothing else.
"""
from __future__ import annotations

import os
import shutil
from typing import List

BLOCK_START = "# >>> arova shell hook >>>"
BLOCK_END = "# <<< arova shell hook <<<"
HOOK_DEST = os.path.join(os.path.expanduser("~"), ".arova", "shell_hook.sh")


def _source_hook() -> str:
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "core", "ambience", "shell_hook.sh")
    return here


def rc_files() -> List[str]:
    home = os.path.expanduser("~")
    candidates = [os.path.join(home, ".zshrc"), os.path.join(home, ".bashrc")]
    return [path for path in candidates if os.path.exists(path)]


def install(dry_run: bool = False) -> List[str]:
    actions: List[str] = []
    source = _source_hook()
    if not os.path.exists(source):
        return [f"hook script missing at {source}"]

    os.makedirs(os.path.dirname(HOOK_DEST), exist_ok=True)
    if not dry_run:
        shutil.copyfile(source, HOOK_DEST)
    actions.append(f"copied hook to {HOOK_DEST}")

    block = f"{BLOCK_START}\n[ -f \"{HOOK_DEST}\" ] && source \"{HOOK_DEST}\"\n{BLOCK_END}\n"
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
        actions.append(f"added hook to {rc}")
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
        actions.append(f"removed hook from {rc}")
    if os.path.exists(HOOK_DEST) and not dry_run:
        os.unlink(HOOK_DEST)
        actions.append(f"deleted {HOOK_DEST}")
    return actions or ["no hook installed"]
