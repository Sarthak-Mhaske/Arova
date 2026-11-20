"""Turns a point into a plan, and optionally carries it out.

plan() touches nothing; apply() only runs when the user passes --yes. Recorded
commands are printed, never executed: a point may have come from another
machine or from an agent, so it is untrusted input.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from deskmark.schema import ResumePoint

GUI_EDITORS = ("code", "cursor", "zed", "subl", "code-insiders", "windsurf")
TERMINALS = ("kitty", "wezterm", "alacritty", "ghostty", "gnome-terminal", "konsole", "xterm", "wt", "cmux")


@dataclass
class RestoreAction:
    kind: str                  # "editor" | "file" | "folder" | "url" | "terminal" | "hint"
    target: str
    label: str = ""
    detail: str = ""
    optional: bool = False
    status: str = "planned"
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "label": self.label,
            "detail": self.detail,
            "optional": self.optional,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class RestorePlan:
    point_id: str
    name: str
    actions: List[RestoreAction] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    host_matches: bool = True

    @property
    def launchable(self) -> List[RestoreAction]:
        return [a for a in self.actions if a.kind in ("editor", "file", "folder", "url")]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "name": self.name,
            "host_matches": self.host_matches,
            "actions": [a.to_dict() for a in self.actions],
            "warnings": self.warnings,
        }


def editor_command() -> Optional[List[str]]:
    override = os.environ.get("DESKMARK_EDITOR")
    if override:
        return override.split()
    for candidate in GUI_EDITORS:
        if shutil.which(candidate):
            return [candidate]
    return None


def terminal_command(cwd: str) -> Optional[List[str]]:
    """Best-effort: open a terminal at ``cwd``. Never runs a recorded command."""
    if shutil.which("kitty"):
        return ["kitty", "--directory", cwd]
    if shutil.which("wezterm"):
        return ["wezterm", "start", "--cwd", cwd]
    if shutil.which("alacritty"):
        return ["alacritty", "--working-directory", cwd]
    if shutil.which("gnome-terminal"):
        return ["gnome-terminal", f"--working-directory={cwd}"]
    if shutil.which("konsole"):
        return ["konsole", "--workdir", cwd]
    return None


def plan(point: ResumePoint, include_files: bool = True, include_terminals: bool = True,
         include_urls: bool = True, max_files: int = 8) -> RestorePlan:
    result = RestorePlan(point_id=point.id, name=point.name)

    current_host = (point.host or {}).get("hostname", "")
    if current_host and current_host != _this_host():
        result.host_matches = False
        result.warnings.append(
            f"point was captured on {current_host}; paths may not exist on this machine"
        )
    if point.is_stale():
        result.warnings.append(f"point is {int(point.age_seconds() // 3600)}h old, verify before trusting it")

    editor = editor_command()

    # 1. workspace root, opened once in the editor (or the file manager)
    root_action = None
    if point.repo and os.path.isdir(point.repo.root):
        if editor:
            root_action = RestoreAction("editor", point.repo.root, label=point.repo.name,
                                        detail=f"{' '.join(editor)} {point.repo.root}")
        else:
            root_action = RestoreAction("folder", point.repo.root, label=point.repo.name,
                                        detail="file manager (no GUI editor found)")
    else:
        roots = [f for f in point.files if f.kind == "folder" and f.reason == "terminal-cwd"]
        if roots and os.path.isdir(roots[0].path):
            root_action = RestoreAction("folder", roots[0].path, label=os.path.basename(roots[0].path))
    if root_action:
        result.actions.append(root_action)

    # 2. files that were open or in flight
    if include_files:
        seen = {point.repo.root} if point.repo else set()
        count = 0
        for ref in point.files:
            if count >= max_files:
                break
            if ref.kind != "file" or ref.path in seen:
                continue
            if not os.path.exists(ref.path):
                result.actions.append(RestoreAction("file", ref.path, label=os.path.basename(ref.path),
                                                    status="missing", error="path no longer exists"))
                continue
            seen.add(ref.path)
            count += 1
            detail = f"{' '.join(editor)} {ref.path}" if editor else ref.path
            result.actions.append(RestoreAction("file", ref.path, label=os.path.basename(ref.path),
                                                detail=detail, optional=True))

    # 3. tabs. cheapest and highest signal part of a resume
    if include_urls:
        for tab in point.tabs:
            result.actions.append(RestoreAction("url", tab.url, label=tab.title,
                                                detail=f"[{tab.category}]", optional=True))

    # 4. shells: reopen the directory, never the command
    if include_terminals:
        for term in point.terminals:
            if not os.path.isdir(term.cwd):
                continue
            command = terminal_command(term.cwd)
            result.actions.append(RestoreAction(
                "terminal", term.cwd, label=os.path.basename(term.cwd.rstrip("/")) or term.cwd,
                detail=(" ".join(command) if command else f"cd {term.cwd}"),
                optional=True,
            ))

    # 5. agents: print how to continue. continuing for the human is not our job
    for agent in point.agents:
        result.actions.append(RestoreAction("hint", agent.cwd or "", label=agent.kind,
                                            detail=agent.resume_hint or agent.kind))

    return result


def apply(plan_obj: RestorePlan, dry_run: bool = True,
          include_optional: bool = True) -> List[Dict[str, Any]]:
    """Execute a plan. ``dry_run`` returns what *would* happen."""
    outcomes: List[Dict[str, Any]] = []
    for action in plan_obj.actions:
        if action.status == "missing":
            outcomes.append(action.to_dict())
            continue
        if action.optional and not include_optional:
            action.status = "skipped"
            outcomes.append(action.to_dict())
            continue
        if action.kind == "hint":
            action.status = "hint"
            outcomes.append(action.to_dict())
            continue
        if dry_run:
            action.status = "would-run"
            outcomes.append(action.to_dict())
            continue
        try:
            _execute(action)
            action.status = "launched"
        except Exception as exc:  # pragma: no cover - platform dependent
            action.status = "failed"
            action.error = str(exc)
        outcomes.append(action.to_dict())
    return outcomes


def _execute(action: RestoreAction) -> None:
    editor = editor_command()
    if action.kind in ("editor", "file") and editor:
        _spawn(editor + [action.target])
        return
    if action.kind in ("file", "folder"):
        _open_with_os(action.target)
        return
    if action.kind == "url":
        _open_with_os(action.target)
        return
    if action.kind == "terminal":
        command = terminal_command(action.target)
        if not command:
            raise RuntimeError("no supported terminal emulator found")
        _spawn(command)
        return
    raise RuntimeError(f"unsupported action kind: {action.kind}")


def _spawn(command: List[str]) -> None:
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _open_with_os(target: str) -> None:
    if sys.platform == "darwin":
        _spawn(["open", target])
    elif sys.platform.startswith("win"):
        os.startfile(target)  # type: ignore[attr-defined]
    else:
        if shutil.which("xdg-open"):
            _spawn(["xdg-open", target])
        else:
            raise RuntimeError("xdg-open not available")


def _this_host() -> str:
    import socket
    return socket.gethostname()


def dim_label(label: str) -> str:
    label = (label or "").strip()
    return f"-- {label[:70]}" if label else ""


def format_plan(plan_obj: RestorePlan) -> str:
    lines = [f"Restore plan for “{plan_obj.name}” ({len(plan_obj.actions)} actions)"]
    for warning in plan_obj.warnings:
        lines.append(f"  ! {warning}")
    icons = {"editor": "◧", "file": "▤", "folder": "▣", "url": "◈", "terminal": "▸", "hint": "✦"}
    for action in plan_obj.actions:
        icon = icons.get(action.kind, "·")
        if action.kind == "url":
            body = f"{action.target}  {dim_label(action.label)}"
        elif action.kind == "hint":
            body = f"{action.label}: {action.detail}"
        else:
            body = action.target
            if action.detail and action.detail not in (action.target, ""):
                body = f"{action.target}   -> {action.detail}"
        optional = "  (optional)" if action.optional else ""
        lines.append(f"  {icon} {action.kind:<8} {body}{optional}")
    lines.append("  recorded commands are shown above but never executed.")
    return "\n".join(lines)
