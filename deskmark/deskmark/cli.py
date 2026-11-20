"""The human surface: one command to put your desk back.

``deskmark save`` / ``deskmark resume`` is the whole product in two verbs.
Everything else is a power tool around that pair.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional

from deskmark import __version__, SCHEMA_ID
from deskmark import hooks, store
from deskmark.errors import PointNotFound, ResumeError
from deskmark.capture import capture
from deskmark.packet import DEFAULT_BUDGET_CHARS, human_age, render, render_json
from deskmark.restore import apply as apply_plan
from deskmark.restore import editor_command, format_plan, plan as build_plan
from deskmark.schema import ResumePoint
from deskmark.look import DEFAULT_QUESTION as _LOOK_QUESTION
from deskmark.look import active_window as _active_window
from deskmark.look import ask as _look_ask
from deskmark.look import available_tools as _look_tools
from deskmark.look import capture as _look_capture

TTY = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if TTY else text


def bold(text: str) -> str:
    return _c(text, "1")


def dim(text: str) -> str:
    return _c(text, "2")


def green(text: str) -> str:
    return _c(text, "32")


def yellow(text: str) -> str:
    return _c(text, "33")


def _compact(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_save(args: argparse.Namespace) -> int:
    name = args.name or _default_name()
    result = capture(
        name=name,
        cwd=args.cwd,
        note=args.note or "",
        why=args.why or "",
        next_step=args.next or "",
        window_hours=args.window,
        browser=not args.no_browser,
        agents=not args.no_agents,
    )
    point = result.point
    path = store.save(point)

    if args.json:
        print(json.dumps({"id": point.id, "path": path, "point": point.to_dict()}, indent=2))
        return 0

    print(f"{green('✓')} resume point {bold(point.name)}  "
          f"{_compact(point.size_bytes())} · zero pixels")
    if point.repo:
        repo = point.repo
        state = "clean" if repo.is_clean else ", ".join(filter(None, [
            f"{len(repo.dirty)} modified" if repo.dirty else "",
            f"{len(repo.staged)} staged" if repo.staged else "",
            f"{len(repo.untracked)} new" if repo.untracked else "",
        ]))
        print(f"  {dim('repo')}    {repo.name}@{repo.branch or '?'} ({state})")
    counts = []
    if point.files:
        counts.append(_plural(len(point.files), "file"))
    if point.tabs:
        counts.append(_plural(len(point.tabs), "tab"))
    if point.terminals:
        counts.append(_plural(len(point.terminals), "shell"))
    if point.agents:
        counts.append("agents " + ",".join(sorted({a.kind for a in point.agents})))
    if counts:
        print(f"  {dim('held')}    {' · '.join(counts)}")
    if point.intent.why:
        print(f"  {dim('why')}     {point.intent.why} {dim('(from ' + point.intent.why_source + ')')}")
    if point.intent.next_step:
        print(f"  {dim('next')}    {point.intent.next_step} {dim('(from ' + point.intent.next_source + ')')}")
    else:
        hint = 'nothing recorded — add --next "…" or a TODO in a changed file'
        print(f"  {dim('next')}    {dim(hint)}")
    print(f"  {dim('saved')}   {path}")
    for warning in result.warnings:
        print(f"  {yellow('!')} {dim(warning)}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = store.list_points(include_stale=not args.fresh)
    if args.limit:
        entries = entries[: args.limit]
    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    if not entries:
        print("No resume points yet. Run `deskmark save <name>`.")
        return 0
    print(bold(f"{len(entries)} resume point(s), {_compact(store.total_size_bytes())} on disk"))
    for entry in entries:
        stale = yellow(" STALE") if entry.get("stale") else ""
        print(f"  {entry['id']}  {bold(entry['name'])}{stale}  "
              f"{dim(human_age(entry.get('age_seconds', 0)) + ' · ' + _compact(int(entry.get('size_bytes', 0))))}")
        if entry.get("why"):
            print(f"               {dim('why:')} {entry['why']}")
        if entry.get("next"):
            print(f"               {dim('next:')} {entry['next']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    point = _load(args.ref)
    if args.json:
        print(render_json(point))
        return 0
    print(render(point, budget_chars=args.budget))
    return 0


def cmd_packet(args: argparse.Namespace) -> int:
    point = _load(args.ref)
    sys.stdout.write(render(point, budget_chars=args.budget))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    point = _load(args.ref)
    plan_obj = build_plan(
        point,
        include_files=not args.no_files,
        include_terminals=not args.no_shells,
        include_urls=not args.no_tabs,
    )
    if args.json:
        print(json.dumps(plan_obj.to_dict(), indent=2))
        if not args.yes:
            return 0
    else:
        print(format_plan(plan_obj))
        print()

    if not args.yes:
        print(dim("dry run — nothing was opened. Re-run with --yes to restore."))
        return 0

    outcomes = apply_plan(plan_obj, dry_run=False, include_optional=not args.core_only)
    launched = sum(1 for o in outcomes if o["status"] == "launched")
    failed = [o for o in outcomes if o["status"] == "failed"]
    print(f"{green('✓')} restored {launched} item(s)"
          + (f", {len(failed)} failed" if failed else ""))
    for item in outcomes:
        if item["kind"] == "hint" and item["detail"]:
            print(f"  {dim('agent')} {item['label']}: {bold(item['detail'])}")
        elif item["status"] == "failed":
            print(f"  {yellow('!')} {item['kind']} {item['target']}: {item['error']}")
    if point.intent.next_step:
        print(f"\n  {dim('pick up here:')} {point.intent.next_step}")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from deskmark.mcp import serve
    try:
        serve()
    except KeyboardInterrupt:
        return 0
    return 0


def cmd_gc(args: argparse.Namespace) -> int:
    removed = store.gc(max_points=args.max, max_age_days=args.days)
    print(f"removed {removed} resume point(s); {_compact(store.total_size_bytes())} remain")
    return 0


def cmd_hooks(args: argparse.Namespace) -> int:
    if args.uninstall:
        for line in hooks.uninstall(dry_run=args.dry_run):
            print(f"  {line}")
        return 0
    for line in hooks.install(dry_run=args.dry_run):
        print(f"  {line}")
    if not args.dry_run:
        print(dim("\nopen a new shell for the hook to take effect."))
    return 0


def cmd_look(args: argparse.Namespace) -> int:
    """One screenshot, one question, one answer. Nothing is stored."""
    question = " ".join(args.question or []).strip() or _LOOK_QUESTION
    context = ""
    if args.window:
        try:
            window = _active_window()
            context = f"The focused window is {window.describe()}.\n\n"
        except ResumeError:
            context = ""

    image = args.image
    method = "given"
    if not image:
        shot = _look_capture()
        image, method = shot.path, shot.method

    answer = _look_ask(question, image=image, provider=args.provider, model=args.model)
    text = answer.text

    if args.json:
        print(json.dumps({
            "question": question,
            "answer": text,
            "provider": answer.provider,
            "model": answer.model,
            "ms": answer.ms,
            "image": image,
            "captured_with": method,
            "image_bytes": answer.image_bytes,
        }, indent=2))
        return 0

    print(text)
    print("")
    print(_c(f"  {answer.provider}/{answer.model} · {answer.ms}ms · {answer.image_bytes // 1024} KB "
             f"· captured with {method} · image at {image}", "2"))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks: List[tuple] = []

    checks.append(("git", bool(shutil.which("git")), "needed for repo state"))
    editor = editor_command()
    checks.append(("editor", bool(editor), " ".join(editor) if editor else "set DESKMARK_EDITOR (e.g. code)"))

    # Same function the reader uses. Recomputing the path here is how doctor
    # ends up telling you to install a hook that is already installed.
    from deskmark.providers.terminal import log_path

    hook_log = log_path()
    checks.append(("shell hook", os.path.exists(hook_log),
                   hook_log if os.path.exists(hook_log) else "run `deskmark hooks`"))

    try:
        from deskmark.providers.history import read_recent
        tabs, redactions, profiles = read_recent(limit=1, max_age_hours=24 * 365)
        detail = (f"{profiles} profile(s) found" if profiles
                  else "no chrome/brave/chromium/edge/firefox profile found")
        if redactions:
            detail += f" · {sum(int(r.split('×')[-1]) for r in redactions if '×' in r)} page(s) withheld by policy"
        checks.append(("browser history", profiles > 0, detail))
    except Exception as exc:
        checks.append(("browser history", False, str(exc)))

    claude_dir = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    checks.append(("claude sessions", os.path.isdir(claude_dir),
                   "used to recover agent session ids" if os.path.isdir(claude_dir) else "not found (optional)"))

    tools = _look_tools()
    checks.append(("screenshot", bool(tools),
                   (", ".join(tools) + " (run `deskmark look` to test it)") if tools
                   else "none found — install grim (Wayland) or scrot (X11)"))
    if args.look_keys:
        keyed = [name for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
                 if os.environ.get(name)]
        checks.append(("vision key", bool(keyed), ", ".join(keyed) if keyed else "set GEMINI_API_KEY for `deskmark look`"))

    checks.append(("store", True, store.points_dir()))
    points = store.list_points()
    checks.append(("resume points", True, f"{len(points)} saved, {_compact(store.total_size_bytes())}"))

    print(bold(f"deskmark {__version__} · {SCHEMA_ID}"))
    for name, ok, detail in checks:
        mark = green("✓") if ok else yellow("·")
        print(f"  {mark} {name:<16} {dim(detail)}")
    print()
    print(dim("MCP: add this to your agent's MCP config →"))
    print(dim(f'  {{"mcpServers": {{"deskmark": {{"command": "deskmark", "args": ["mcp"]}}}}}}'))
    return 0


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _default_name() -> str:
    import time as _time
    base = os.path.basename(os.getcwd()) or "session"
    return f"{base}-{_time.strftime('%H%M')}"


def _load(ref: Optional[str]) -> ResumePoint:
    if ref:
        try:
            return store.load(ref)
        except PointNotFound:
            # Ergonomics: allow `deskmark show ./point.json`. Paths are only ever
            # accepted from the CLI, never from HTTP or MCP.
            if os.sep in ref or ref.endswith(".json"):
                return store.load(ref, allow_path=True)
            raise
    entry = store.latest()
    if not entry:
        raise PointNotFound(
            "no resume points yet",
            hint="run `deskmark save <name>` to create one",
        )
    return store.load(entry["id"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deskmark",
        description="Resume points for your whole desk. Zero pixels, one command.",
    )
    parser.add_argument("--version", action="version", version=f"deskmark {__version__} ({SCHEMA_ID})")
    sub = parser.add_subparsers(dest="command", required=True)

    save = sub.add_parser("save", help="capture a resume point of the current work")
    save.add_argument("name", nargs="?", help="intent-shaped name, e.g. checkout-idempotency")
    save.add_argument("-C", "--cwd", default=None, help="directory to capture (default: cwd)")
    save.add_argument("-n", "--note", default="", help="why this work exists")
    save.add_argument("--why", default="", help="override the inferred why")
    save.add_argument("--next", default="", help="the single next action")
    save.add_argument("--window", type=float, default=12.0, help="hours of history to consider")
    save.add_argument("--no-browser", action="store_true", help="do not read browser history")
    save.add_argument("--no-agents", action="store_true", help="do not scan for running agents")
    save.add_argument("--json", action="store_true")
    save.set_defaults(func=cmd_save)

    ls = sub.add_parser("list", help="list resume points")
    ls.add_argument("--limit", type=int, default=0)
    ls.add_argument("--fresh", action="store_true", help="hide stale points")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="show one resume point")
    show.add_argument("ref", nargs="?", default=None)
    show.add_argument("--budget", type=int, default=DEFAULT_BUDGET_CHARS)
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)

    packet = sub.add_parser("packet", help="print the agent-ready context packet")
    packet.add_argument("ref", nargs="?", default=None)
    packet.add_argument("--budget", type=int, default=DEFAULT_BUDGET_CHARS)
    packet.set_defaults(func=cmd_packet)

    resume = sub.add_parser("resume", help="restore a resume point (dry run by default)")
    resume.add_argument("ref", nargs="?", default=None)
    resume.add_argument("--yes", action="store_true", help="actually open things")
    resume.add_argument("--no-files", action="store_true")
    resume.add_argument("--no-tabs", action="store_true")
    resume.add_argument("--no-shells", action="store_true")
    resume.add_argument("--core-only", action="store_true", help="skip optional items")
    resume.add_argument("--json", action="store_true")
    resume.set_defaults(func=cmd_resume)

    mcp = sub.add_parser("mcp", help="run the MCP server on stdio")
    mcp.set_defaults(func=cmd_mcp)

    gc = sub.add_parser("gc", help="delete old resume points")
    gc.add_argument("--max", type=int, default=200)
    gc.add_argument("--days", type=float, default=30.0)
    gc.set_defaults(func=cmd_gc)

    hook = sub.add_parser("hooks", help="install or remove the shell hook")
    hook.add_argument("--uninstall", action="store_true")
    hook.add_argument("--dry-run", action="store_true")
    hook.set_defaults(func=cmd_hooks)

    look = sub.add_parser("look", help="ask about what is on the screen (one shot, your own key)")
    look.add_argument("question", nargs="*", help="what to ask (default: explain this screen)")
    look.add_argument("--image", default=None, help="use this file instead of taking a screenshot")
    look.add_argument("--window", action="store_true", help="include the focused window in the question")
    look.add_argument("--provider", default=None, choices=["gemini", "openai", "anthropic"])
    look.add_argument("--model", default=None)
    look.add_argument("--json", action="store_true")
    look.set_defaults(func=cmd_look)

    doctor = sub.add_parser("doctor", help="check what this machine can capture")
    doctor.add_argument("--look-keys", action="store_true", help="also report whether a vision key is set")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except ResumeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
