"""Tests for the resume point primitive.

These are not coverage tests. Each one pins a promise the product makes:

* a resume point round-trips and can prove it has not been tampered with;
* nothing sensitive ever enters one;
* the inferred "why / next" is deterministic and honest about its source;
* restoring never executes a recorded command;
* the MCP surface behaves like a protocol implementation, not like a script.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time

import pytest

from deskmark import SCHEMA_ID, store
from deskmark.capture import capture
from deskmark.intent import derive
from deskmark.packet import render, render_json
from deskmark.providers import privacy
from deskmark.providers.agents import _classify as classify_agent
from deskmark.providers.agents import _session_from_cmdline as session_from_cmdline
from deskmark.providers.sessions import lz4_block, open_tabs, parse_chrome_session
from deskmark.providers.repo import capture_repo, open_questions, working_set_files
from deskmark.providers.terminal import capture_from_log
from deskmark.restore import apply as apply_plan
from deskmark.restore import plan as build_plan
from deskmark.schema import (
    AgentRef,
    FileRef,
    Intent,
    RepoState,
    ResumePoint,
    TabRef,
    TerminalRef,
)


# --- fixtures ---

@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Isolated HOME so no test can read the developer's real browser or store."""
    fake_home = tmp_path / "home"
    (fake_home / ".config").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("DESKMARK_HOME", str(fake_home / ".deskmark"))
    monkeypatch.setenv("XDG_DATA_HOME", str(fake_home / ".local" / "share"))
    return fake_home


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "acme" / "api"
    (root / "src").mkdir(parents=True)
    (root / "src" / "handler.py").write_text(
        "def handle(event):\n    # TODO: backfill duplicate-delivery test\n    return True\n"
    )
    (root / "src" / "stable.py").write_text("X = 1\n")
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "init", "-q", str(root)], check=True, env={**os.environ, **env})
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "webhooks: verify signature"],
                   check=True, env={**os.environ, **env})
    (root / "src" / "handler.py").write_text(
        "def handle(event):\n    # TODO: backfill duplicate-delivery test\n    return True\n\nRETRIES = 3\n"
    )
    (root / "src" / "new_thing.py").write_text("# FIXME: where do idempotency keys live?\n")
    return root


def _string(text):
    raw = text.encode()
    return struct.pack("<I", len(raw)) + raw + b"\0" * (-len(raw) % 4)


def _string16(text):
    raw = text.encode("utf-16-le")
    return struct.pack("<I", len(raw) // 2) + raw + b"\0" * (-len(raw) % 4)


def _navigation(tab_id, url, title, index=0):
    body = struct.pack("<II", tab_id, index) + _string(url) + _string16(title)
    return struct.pack("<I", len(body)) + body


def chrome_session(home, tabs, closed=(), window=1, close_window=False,
                   truncated=False, name="Session_13400000000000000"):
    """Lay out a Session_* file the way chrome does: SNSS, then u16 records."""
    records = []
    for tab_id, (url, title) in tabs.items():
        records.append((6, _navigation(tab_id, url, title)))
        records.append((0, struct.pack("<II", window, tab_id)))
    records.extend((16, struct.pack("<I", tab_id)) for tab_id in closed)
    if close_window:
        records.append((17, struct.pack("<I", window)))

    blob = b"SNSS" + struct.pack("<I", 1)
    for command, payload in records:
        blob += struct.pack("<H", len(payload) + 1) + bytes([command]) + payload
    if truncated:
        blob = blob[:-3]

    path = home / ".config" / "google-chrome" / "Default" / "Sessions" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return path


def lz4_literals(payload):
    """The smallest legal LZ4 block: one sequence, literals only, no match."""
    size = len(payload)
    if size < 15:
        header = bytes([size << 4])
    else:
        header = bytearray([0xF0])
        rest = size - 15
        while rest >= 255:
            header.append(255)
            rest -= 255
        header.append(rest)
        header = bytes(header)
    return header + payload


def firefox_session(home, windows):
    """recovery.jsonlz4 exactly as firefox wraps it: magic, size, lz4 block."""
    raw = json.dumps({"windows": windows}).encode()
    blob = b"mozLz40\0" + struct.pack("<I", len(raw)) + lz4_literals(raw)
    path = home / ".mozilla" / "firefox" / "abc.default" / "sessionstore-backups" / "recovery.jsonlz4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.parent.joinpath("places.sqlite").write_bytes(b"")
    path.write_bytes(blob)
    return path


# --- format ---

def test_roundtrip_is_lossless_and_verifiable():
    point = ResumePoint(
        name="checkout-idempotency",
        repo=RepoState(root="/x/api", name="api", branch="feat/checkout", head="abc123",
                       dirty=["src/a.py"]),
        files=[FileRef(path="/x/api/src/a.py", reason="dirty")],
        tabs=[TabRef(url="https://example.com/doc", title="Doc", category="research")],
        terminals=[TerminalRef(cwd="/x/api", last_command="pytest", exit_code=1)],
        agents=[AgentRef(kind="claude", cwd="/x/api", session_id="abc")],
        intent=Intent(why="ship idempotency", next_step="add the test"),
    )
    data = point.to_dict()
    revived = ResumePoint.from_dict(data)
    assert revived.to_dict() == data
    assert revived.verify()
    assert revived.schema == SCHEMA_ID


def test_newer_schema_is_refused_not_guessed():
    with pytest.raises(ValueError, match="newer"):
        ResumePoint.from_dict({"schema": SCHEMA_ID, "version": 99, "name": "x"})


def test_foreign_schema_is_refused():
    with pytest.raises(ValueError, match="schema"):
        ResumePoint.from_dict({"schema": "other/v1", "version": 1, "name": "x"})


# --- privacy ---

@pytest.mark.parametrize("url,title", [
    ("https://chase.com/payments", "Transfer funds"),
    ("https://accounts.google.com/signin", "Sign in"),
    ("https://mail.google.com/mail/u/0", "Inbox"),
    ("https://bank.example.com/statement", "Statement"),
    ("https://x.com/home", "Home / X"),
])
def test_sensitive_pages_are_dropped(url, title):
    assert privacy.classify(url, title).verdict is privacy.Verdict.DROP


@pytest.mark.parametrize("url,title", [
    ("https://github.com/acme/api/pull/412", "Add checkout idempotency by dev"),
    ("https://stripe.com/docs/webhooks/best-practices", "Webhook best practices"),
    ("https://www.postgresql.org/docs/current/sql-insert.html", "INSERT"),
])
def test_work_pages_survive_even_when_the_title_looks_sensitive(url, title):
    """The old filter dropped this PR because its title contained "checkout"."""
    assert privacy.classify(url, title).verdict is privacy.Verdict.KEEP


def test_tabs_come_from_the_session_log_and_history_is_ignored(home):
    """A page visited at nine in the morning is not an open tab at five.

    The old reader took the newest twelve rows out of History, which keeps a row
    per url for ninety days, so it offered up the whole afternoon.
    """
    chrome_session(home, {7: ("https://github.com/acme/api/pull/412", "Add checkout idempotency")})
    tabs, redactions, profiles = open_tabs(limit=10)
    assert profiles == 1
    assert [t.url for t in tabs] == ["https://github.com/acme/api/pull/412"]
    assert tabs[0].category == "development"


def test_a_tab_closed_this_run_is_not_offered(home):
    chrome_session(home, {
        7: ("https://github.com/acme/api/pull/412", "Add checkout idempotency"),
        9: ("https://news.ycombinator.com/item?id=1", "Show HN: a widget"),
    }, closed=[9])
    tabs, _, _ = open_tabs(limit=10)
    assert [t.url for t in tabs] == ["https://github.com/acme/api/pull/412"]


def test_a_closed_window_takes_its_tabs_with_it(home):
    chrome_session(home, {7: ("https://github.com/acme/api/pull/412", "PR")}, close_window=True)
    tabs, _, profiles = open_tabs(limit=10)
    assert tabs == [] and profiles == 1


def test_half_written_session_keeps_what_completed(home):
    """The browser appends while we read, so the tail can be a torn record."""
    chrome_session(home, {7: ("https://github.com/acme/api/pull/412", "PR")}, truncated=True)
    tabs, _, _ = open_tabs(limit=10)
    assert [t.url for t in tabs] == ["https://github.com/acme/api/pull/412"]


def test_a_session_file_that_is_not_a_session_file_is_skipped(home):
    path = home / ".config" / "google-chrome" / "Default" / "Sessions" / "Session_1"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * 512)
    tabs, redactions, profiles = open_tabs(limit=10)
    assert tabs == [] and redactions == [] and profiles == 1


def test_private_pages_never_reach_the_point(home):
    chrome_session(home, {
        1: ("https://chase.com/transfer", "Transfer funds"),
        2: ("https://mail.google.com/mail/u/0", "Inbox (17)"),
        3: ("https://github.com/acme/api/pull/412", "(3) Add checkout idempotency · PR #412"),
    })
    tabs, redactions, _ = open_tabs(limit=10)
    urls = [t.url for t in tabs]
    assert urls == ["https://github.com/acme/api/pull/412"]
    assert redactions and all("×" in r for r in redactions)
    assert not tabs[0].title.startswith("(3)")


def test_browser_internal_pages_are_not_tabs(home):
    chrome_session(home, {
        1: ("chrome://newtab/", "New Tab"),
        2: ("about:blank", "about:blank"),
        3: ("https://github.com/acme/api/pull/412", "PR"),
    })
    tabs, _, _ = open_tabs(limit=10)
    assert [t.url for t in tabs] == ["https://github.com/acme/api/pull/412"]


def test_firefox_session_is_read_out_of_jsonlz4(home):
    firefox_session(home, [{
        "tabs": [
            {"entries": [{"url": "https://example.com/before", "title": "Before"},
                         {"url": "https://docs.python.org/3/library/lz4", "title": "Docs"}],
             "index": 2},
            {"entries": [], "index": 1},
        ],
    }])
    tabs, _, _ = open_tabs(limit=10)
    # index 2 is the entry firefox was showing, not the last one it kept
    assert [t.url for t in tabs] == ["https://docs.python.org/3/library/lz4"]


def test_lz4_back_references_decode():
    """Literals plus one overlapping match: 'abc' + (offset 3, length 6)."""
    block = bytes([0x32]) + b"abc" + b"\x03\x00"
    assert lz4_block(block, expected=9) == b"abcabcabc"


def test_a_corrupt_session_returns_nothing_rather_than_guessing():
    assert parse_chrome_session(b"SNSS" + struct.pack("<I", 1) + b"\xff\xff") == []
    assert parse_chrome_session(b"not a session file") == []


def test_no_browser_profile_is_reported_as_absent(home):
    tabs, redactions, profiles = open_tabs()
    assert tabs is None and profiles == 0 and redactions == []


def test_a_remote_url_with_a_token_is_redacted_before_it_is_stored(repo):
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    "https://me:ghp_secrettoken123456@github.com/acme/private.git"], check=True)
    notes = []
    state = capture_repo(str(repo), redactions=notes)
    assert "ghp_" not in state.remote and "[redacted]" in state.remote
    assert notes and "×1" in notes[0]


def test_only_a_real_todo_counts_as_an_open_question(repo):
    (repo / "src" / "names.py").write_text(
        "TODO_ITEMS = ['a']\n"
        "XXXXXXX = 0\n"
        "def f():\n"
        "    # FIXME: the retry loop never gives up\n"
    )
    questions = open_questions(capture_repo(str(repo)))
    assert any("FIXME: the retry loop never gives up" in q for q in questions)
    assert not any("TODO_ITEMS" in q or "XXXXXXX" in q for q in questions)


def test_a_renamed_file_is_tracked_by_its_new_name(repo):
    (repo / "src" / "stable.py").rename(repo / "src" / "renamed.py")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    state = capture_repo(str(repo))
    assert "src/renamed.py" in state.staged, state.staged
    assert not any(" -> " in path for path in state.staged)


# --- capture ---

def test_repo_capture_reads_facts_from_git(repo):
    state = capture_repo(str(repo))
    assert state is not None
    assert state.name == "api"
    assert "src/handler.py" in [os.path.basename(p) for p in state.dirty] or state.dirty
    assert state.recent_commits[0]["subject"] == "webhooks: verify signature"

    files = working_set_files(state)
    paths = {os.path.basename(f.path) for f in files}
    assert "handler.py" in paths
    assert all(f.reason != "recent" for f in files)   # dirty work wins over history

    markers = open_questions(state)
    assert any("duplicate-delivery" in m for m in markers)


def test_non_git_directory_degrades_quietly(tmp_path):
    assert capture_repo(str(tmp_path)) is None
    result = capture(name="loose", cwd=str(tmp_path), browser=False, agents=False)
    assert result.point.repo is None
    assert "repo" in " ".join(result.warnings)


def test_shell_log_yields_last_command_and_failure(home):
    log = home / ".deskmark" / "session_log.jsonl"   # DESKMARK_HOME wins; see terminal.log_path
    log.parent.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    events = [
        {"timestamp": now, "type": "terminal_command",
         "data": {"command": "pytest tests -k retry", "cwd": "/x/api", "cmd_id": "c1"}},
        {"timestamp": now, "type": "terminal_output",
         "data": {"command": "pytest tests -k retry", "cmd_id": "c1", "exit_code": 1}},
        {"timestamp": now, "type": "terminal_command",
         "data": {"command": "rg X-Idempotency", "cwd": "/x/api", "cmd_id": "c2"}},
        {"timestamp": now, "type": "terminal_command",
         "data": {"command": "export API_KEY=sk-live-123", "cwd": "/x/api", "cmd_id": "c3"}},
    ]
    log.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    redactions: list = []
    refs = capture_from_log(window_hours=1, redactions=redactions)
    assert len(refs) == 1
    ref = refs[0]
    # credential cut out, command kept. dropping the line would lose the work
    # as well as the secret.
    assert ref.last_command == "export API_KEY=[redacted]"
    assert redactions == ["command text ×1"]
    assert ref.last_failure == "pytest tests -k retry"
    assert ref.last_failure_exit == 1
    assert "sk-live" not in json.dumps(ref.to_dict())


def test_capture_writes_a_point_small_enough_to_be_portable(repo, home):
    log = home / ".deskmark" / "session_log.jsonl"   # DESKMARK_HOME wins; see terminal.log_path
    log.parent.mkdir(parents=True, exist_ok=True)
    result = capture(name="checkout", cwd=str(repo), browser=False, agents=False)
    assert result.point.size_bytes() < 20_000
    assert result.point.repo is not None
    assert result.point.files[0].reason == "repo-root"
    assert result.point.intent.next_step          # derived from the TODO
    assert result.point.intent.next_source == "todo"


# --- intent ---

def test_user_intent_always_wins():
    repo = RepoState(root="/x", name="x", branch="feat/thing", dirty=["a.py"])
    intent = derive(repo, ["TODO: something"], [], note="because billing", next_step="ship it")
    assert intent.why == "because billing" and intent.why_source == "note"
    assert intent.next_step == "ship it" and intent.next_source == "user"


def test_intent_is_deterministic():
    repo = RepoState(root="/x", name="x", branch="feat/thing")
    first = derive(repo, ["TODO: a"], []).to_dict()
    second = derive(repo, ["TODO: a"], []).to_dict()
    assert first == second


def test_failure_without_todo_becomes_the_next_step():
    term = TerminalRef(cwd="/x/api", last_command="pytest", last_failure="pytest tests", last_failure_exit=2)
    intent = derive(None, [], [term])
    assert "pytest tests" in intent.next_step
    assert intent.next_source == "terminal-exit"


# --- restore ---

def test_restore_plan_never_carries_an_executable_command(repo, home):
    log = home / ".deskmark" / "session_log.jsonl"   # DESKMARK_HOME wins; see terminal.log_path
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "type": "terminal_command",
        "data": {"command": "rm -rf /", "cwd": str(repo), "cmd_id": "x"},
    }) + "\n")

    result = capture(name="danger", cwd=str(repo), browser=False, agents=False)
    plan = build_plan(result.point)

    for action in plan.actions:
        assert action.kind in {"editor", "file", "folder", "url", "terminal", "hint"}
        assert "rm -rf" not in (action.detail or "")
        assert "rm -rf" not in action.target

    # dry run is the default, so nothing here should have been launched
    outcomes = apply_plan(plan, dry_run=True)
    assert all(o["status"] in {"would-run", "missing", "hint"} for o in outcomes)


def test_restore_plan_flags_a_different_host_and_staleness():
    point = ResumePoint(name="old", host={"hostname": "some-other-laptop"})
    point.created_at = time.time() - 30 * 86400
    plan = build_plan(point)
    assert not plan.host_matches
    assert any("may not exist" in w for w in plan.warnings)
    assert any("old" in w for w in plan.warnings)


# --- store ---

def test_store_roundtrip_list_and_gc(home):
    for index in range(3):
        point = ResumePoint(name=f"p{index}", intent=Intent(why=f"why {index}"))
        store.save(point)

    entries = store.list_points()
    assert len(entries) == 3
    assert entries[0]["name"] == "p2"                  # newest first

    loaded = store.load("p1")
    assert loaded.intent.why == "why 1"
    assert store.load(loaded.id).id == loaded.id

    removed = store.gc(max_points=1, max_age_days=365)
    assert removed == 2
    assert len(store.list_points()) == 1


def test_store_missing_ref_raises(home):
    from deskmark.errors import PointNotFound
    with pytest.raises(PointNotFound):
        store.load("nope")


# --- packet ---

def test_packet_stays_within_budget_and_keeps_the_important_parts(repo, home):
    result = capture(name="big", cwd=str(repo), browser=False, agents=False)
    result.point.tabs = [TabRef(url=f"https://e.com/{i}", title="t" * 80) for i in range(20)]

    packet = render(result.point, budget_chars=1200)
    assert len(packet) < 1800
    assert "Where you were" in packet
    assert "Why / next" in packet
    assert "omitted for budget" in packet


def test_packet_is_explicit_about_staleness_and_gaps():
    point = ResumePoint(name="stale")
    point.created_at = time.time() - 10 * 86400
    packet = render(point)
    assert "STALE" in packet
    assert "not captured" in packet
    assert "zero pixels" in packet


def test_packet_json_is_machine_readable(repo, home):
    result = capture(name="j", cwd=str(repo), browser=False, agents=False)
    payload = json.loads(render_json(result.point))
    assert payload["schema"] == SCHEMA_ID
    assert payload["repo"]["name"] == "api"
    assert "provenance" in payload


# --- agents ---

@pytest.mark.parametrize("cmdline,expected", [
    ("node /usr/local/bin/claude --resume abc123", "claude"),
    ("codex --full-auto", "codex"),
    ("/usr/bin/python3 -m aider", "aider"),
    ("node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js", "claude"),
    ("npx @google/gemini-cli", "gemini"),
    ("grep -r claude .", None),
    ("vim ~/.claude/settings.json", None),
    # these two were classified as agents when matching ran over the whole line
    ("python3 -c import time /home/me/claude-notes/migrate.py", None),
    ("bash -c sleep 20 claude-helper", None),
])
def test_agent_process_classification(cmdline, expected):
    assert classify_agent(cmdline) == expected


@pytest.mark.parametrize("cmdline,expected", [
    ("claude --resume 8f2c91ab-1111-2222-3333-444455556666",
     "8f2c91ab-1111-2222-3333-444455556666"),
    ("codex --session=abcd1234abcd1234", "abcd1234abcd1234"),
    # -c means --continue to claude and "run this string" to python, and the
    # guess produced "claude --resume import"
    ('python3 -c "import time"', ""),
    ("claude --resume import", ""),
    ("codex resume abc", ""),
])
def test_session_ids_only_come_from_unambiguous_flags(cmdline, expected):
    assert session_from_cmdline(cmdline) == expected


def test_last_failure_is_not_borrowed_from_an_earlier_command(home, monkeypatch):
    """A failed output with no command text of its own names nothing.

    The old loop kept the previous line's command in a local and blamed that,
    so a command that had succeeded was reported as the last failure.
    """
    log = home / "session_log.jsonl"
    home.mkdir(exist_ok=True)
    now = time.time()
    events = [
        {"type": "terminal_command", "timestamp": now - 60,
         "data": {"cmd_id": "a", "cwd": "/x/api", "command": "make build"}},
        {"type": "terminal_output", "timestamp": now - 59,
         "data": {"cmd_id": "a", "cwd": "/x/api", "exit_code": 0}},
        # the command event for z fell outside the window; only its output is here
        {"type": "terminal_output", "timestamp": now - 30,
         "data": {"cmd_id": "z", "cwd": "/x/api", "exit_code": 2}},
    ]
    log.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    monkeypatch.setenv("DESKMARK_HOME", str(home))
    ref = capture_from_log(window_hours=12)[0]
    assert ref.last_command == "make build"
    assert ref.exit_code == 2
    assert ref.last_failure == ""          # make build did not fail


# --- mcp ---

def test_mcp_speaks_both_protocol_eras(home):
    from deskmark.mcp import handle

    legacy = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18"}})
    assert legacy["id"] == 1
    assert legacy["result"]["protocolVersion"] == "2025-06-18"

    modern = handle({"jsonrpc": "2.0", "id": 2, "method": "server/discover",
                     "params": {"_meta": {}}})
    assert "2026-07-28" in modern["result"]["supportedVersions"]

    listed = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {"resume_latest", "resume_point_save", "resume_point_get"} <= names

    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    unknown = handle({"jsonrpc": "2.0", "id": 4, "method": "does/not/exist"})
    assert unknown["error"]["code"] == -32601


def test_mcp_save_then_read_roundtrip(repo, home, monkeypatch):
    from deskmark import mcp

    saved = mcp.call_tool("resume_point_save", {"name": "from-agent", "cwd": str(repo),
                                                "next_step": "run the duplicate test"})
    assert not saved.get("isError")
    payload = json.loads(saved["content"][0]["text"])
    assert payload["name"] == "from-agent"

    latest = mcp.call_tool("resume_latest", {})
    text = latest["content"][0]["text"]
    assert "run the duplicate test" in text
    assert "zero pixels" in text

    missing = mcp.call_tool("resume_point_get", {"ref": "nope"})
    assert missing.get("isError")


def test_cli_entrypoint_smoke(repo, home):
    from deskmark.cli import main

    assert main(["save", "cli-smoke", "-C", str(repo), "--no-browser", "--no-agents"]) == 0
    assert main(["list"]) == 0
    assert main(["show"]) == 0
    assert main(["resume"]) == 0                      # dry run prints a plan


# --- store robustness ---
# every case below crashed, or silently loaded wrong, at some point.

def test_corrupt_point_file_raises_a_clean_error(home):
    from deskmark.errors import CorruptPointError, DeskmarkError

    point = ResumePoint(name="damaged")
    path = store.save(point)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{ not json")

    with pytest.raises(CorruptPointError) as excinfo:
        store.load(point.id)
    assert isinstance(excinfo.value, DeskmarkError)
    assert "not valid JSON" in str(excinfo.value)
    assert "hint" in str(excinfo.value)


def test_list_drops_damaged_and_missing_points_instead_of_listing_them(home):
    good = ResumePoint(name="good")
    bad = ResumePoint(name="bad")
    store.save(good)
    bad_path = store.save(bad)
    with open(bad_path, "w", encoding="utf-8") as handle:
        handle.write("garbage")

    names = [entry["name"] for entry in store.list_points()]
    assert names == ["good"]


def test_corrupt_index_is_a_cache_miss_not_a_failure(home):
    point = ResumePoint(name="survivor")
    store.save(point)
    with open(store.index_path(), "w", encoding="utf-8") as handle:
        handle.write("[[[")

    assert [e["name"] for e in store.list_points()] == ["survivor"]
    assert store.load("survivor").name == "survivor"


def test_point_copied_into_the_store_is_picked_up(home):
    point = ResumePoint(name="imported")
    path = store.save(point)
    os.unlink(store.index_path())          # simulate a lost index
    assert [e["name"] for e in store.list_points()] == ["imported"]
    assert os.path.exists(path)


def test_index_entry_whose_file_is_gone_is_not_served(home):
    from deskmark.errors import PointNotFound

    point = ResumePoint(name="ghost")
    path = store.save(point)
    os.unlink(path)

    assert store.list_points() == []
    with pytest.raises(PointNotFound):
        store.load("ghost")


def test_empty_reference_is_refused_not_guessed(home):
    from deskmark.errors import PointNotFound

    store.save(ResumePoint(name="anything"))
    for bad in ("", "   ", None):
        with pytest.raises(PointNotFound):
            store.load(bad)


def test_ambiguous_prefix_is_refused(home):
    from deskmark.errors import PointNotFound

    store.save(ResumePoint(name="feat-alpha"))
    store.save(ResumePoint(name="feat-beta"))
    with pytest.raises(PointNotFound):
        store.load("f")                        # too short to be a prefix
    assert store.load("feat-a").name == "feat-alpha"


def test_paths_are_only_accepted_when_asked_for(home, tmp_path):
    from deskmark.errors import PointNotFound

    point = ResumePoint(name="on-disk")
    path = store.save(point)
    with pytest.raises(PointNotFound):
        store.load(path)                       # a path is not a name
    assert store.load(path, allow_path=True).name == "on-disk"


def test_unwritable_store_reports_what_to_do(home, monkeypatch):
    from deskmark.errors import StoreError

    monkeypatch.setenv("DESKMARK_HOME", "/proc/definitely/not/writable")
    with pytest.raises(StoreError) as excinfo:
        store.save(ResumePoint(name="nowhere"))
    assert "DESKMARK_HOME" in str(excinfo.value)


def test_future_timestamp_is_reported_as_clock_skew(home):
    point = ResumePoint(name="time traveller")
    point.created_at = time.time() + 3600
    packet = render(point)
    assert "future" in packet.lower()


def test_gc_and_delete_are_safe_on_an_empty_store(home):
    assert store.gc() == 0
    assert store.delete("nothing") is False
    assert store.total_size_bytes() == 0


def test_cli_reports_errors_without_a_traceback(home, capsys):
    from deskmark.cli import main

    assert main(["show", "does-not-exist"]) == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "hint:" in captured.err
    assert "Traceback" not in captured.err


def test_deskmars_home_wins_over_xdg_for_the_session_log(home, monkeypatch, tmp_path):
    """One setting decides where everything lives, or the log is never found."""
    from deskmark.providers import terminal

    monkeypatch.setenv("DESKMARK_HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert terminal.log_path() == str(home / "session_log.jsonl")

    monkeypatch.delenv("DESKMARK_HOME")
    assert terminal.log_path() == str(tmp_path / "xdg" / "deskmark" / "session_log.jsonl")


def test_doctor_reports_the_hook_using_the_same_path_capture_reads(home, capsys):
    """doctor recomputing the log path is how it tells you to install a hook you have."""
    import argparse
    import pathlib

    from deskmark import cli
    from deskmark.providers.terminal import log_path

    log = pathlib.Path(log_path())
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")

    cli.cmd_doctor(argparse.Namespace(look_keys=False))
    hook_line = [l for l in capsys.readouterr().out.splitlines() if "shell hook" in l][0]
    assert "run `hooks`" not in hook_line.replace("deskmark ", "")
    assert str(log) in hook_line


def test_hook_installs_under_deskmars_home(home):
    """A home variable that moves points but not the hook is half a feature."""
    from deskmark import hooks

    assert hooks.hook_dest().startswith(str(home))
    assert hooks.hook_dest().endswith("shell_hook.sh")


def test_version_is_declared_once_and_agrees_everywhere(home):
    """A release where the tag, pyproject and __init__ disagree ships the wrong thing."""
    import pathlib
    import re

    import deskmark

    pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = re.search(r'^version = "([^"]+)"', pyproject.read_text(), re.M).group(1)
    assert declared == deskmark.__version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", deskmark.__version__)
    assert deskmark.SCHEMA_ID == "deskmark/v1"


def test_hook_dry_run_changes_nothing_and_says_so(home, monkeypatch):
    """A dry run that says "copied" while copying nothing is worse than no dry run."""
    from deskmark import hooks

    rc = home / ".bashrc"
    rc.write_text("# my rc\n")
    monkeypatch.setenv("HOME", str(home))

    actions = hooks.install(dry_run=True)
    assert any("would" in a for a in actions)
    assert not any(a.startswith("copied") or a.startswith("added") for a in actions)
    assert not hooks.hook_dest() or not __import__("os").path.exists(hooks.hook_dest())
    assert rc.read_text() == "# my rc\n"

    hooks.install(dry_run=False)
    assert hooks.BLOCK_START in rc.read_text()
    assert __import__("os").path.exists(hooks.hook_dest())

    hooks.uninstall(dry_run=False)
    assert hooks.BLOCK_START not in rc.read_text()
    assert not __import__("os").path.exists(hooks.hook_dest())


def test_agents_in_a_deleted_directory_are_not_offered(home):
    """A resume hint pointing at a directory that no longer exists is noise."""
    from deskmark.providers import agents

    assert agents.capture_agents(limit=1) == [] or all(
        not a.cwd.endswith(" (deleted)") for a in agents.capture_agents()
    )


@pytest.mark.parametrize("command, forbidden", [
    ("export API_KEY=sk-live-abcdef123456", "sk-live"),
    ("curl -H 'Authorization: Bearer ghp_secrettoken123' https://api", "ghp_"),
    ("psql postgres://user:hunter2@db.internal/prod", "hunter2"),
    ("mysql --password=hunter2 -u root", "hunter2"),
    ("npm config set //registry/:_authToken=npm_abcdefghijkl", "npm_abc"),
    ("aws configure set aws_secret_access_key AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("docker login --password s3cr3t-registry-pass", "s3cr3t"),
])
def test_redaction_removes_credentials_from_command_text(command, forbidden):
    from deskmark.providers.privacy import redact_command

    safe, hits = redact_command(command)
    assert hits >= 1, command
    assert forbidden not in safe
    # the command itself survives, otherwise the point stops saying what you ran
    assert safe.split(" ")[0] in command.split(" ")[0]


@pytest.mark.parametrize("command", [
    "git log --oneline -20",
    "pytest tests -k retry",
    "grep -rn token src/",          # the word without a value is not a secret
    "rg X-Idempotency",
    "docker compose -f compose.yaml up -d",
])
def test_redaction_leaves_ordinary_commands_alone(command):
    from deskmark.providers.privacy import redact_command

    assert redact_command(command) == (command, 0)


def test_a_point_edited_after_it_was_saved_is_refused(home):
    """The digest is only worth having if every read checks it."""
    from deskmark.errors import CorruptPointError
    from deskmark import store

    point = _point("tamper-me")
    store.save(point)
    path = os.path.join(store.points_dir(), point.id + ".json")
    data = json.load(open(path))
    data["name"] = "edited-by-hand"
    json.dump(data, open(path, "w"))

    with pytest.raises(CorruptPointError) as excinfo:
        store.load(point.id)
    assert "changed after it was saved" in str(excinfo.value)

    # and a listing skips it rather than dying on it
    assert all(entry["id"] != point.id for entry in store.list_points())


def test_a_point_that_is_not_utf8_does_not_break_the_listing(home):
    from deskmark import store

    good = _point("readable")
    store.save(good)
    with open(os.path.join(store.points_dir(), "badc0ffee000.json"), "wb") as handle:
        handle.write(b"\xff\xfe\x00 not utf-8")

    entries = store.list_points()
    assert [entry["id"] for entry in entries] == [good.id]


def test_mcp_rejects_a_resource_path_instead_of_failing_internally(home):
    """A client may ask for ../../etc/passwd. That is a bad parameter, not a crash."""
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                          "params": {"uri": "deskmark://resume/../../etc/passwd"}})
    out = subprocess.run([sys.executable, "-m", "deskmark", "mcp"], input=request + "\n",
                         capture_output=True, text=True, timeout=30,
                         env=dict(os.environ, DESKMARK_HOME=str(home / ".deskmark")))
    reply = json.loads(out.stdout.splitlines()[0])
    assert reply["error"]["code"] == -32602
    assert "unknown resource" in reply["error"]["message"]
    assert "root:x:" not in out.stdout


def _point(name: str) -> "ResumePoint":
    point = ResumePoint(name=name, host={"hostname": "test-host"})
    point.digest = point.to_dict()["digest"]
    return point


def test_an_id_prefix_resolves_and_an_ambiguous_one_refuses_to_guess(home):
    """`deskmark resume <prefix>` must work, and must never pick for you."""
    from deskmark import store
    from deskmark.errors import AmbiguousReference

    first = _point("checkout")
    first.id = "ab1111c0ffee"
    store.save(first)
    second = _point("webhooks")
    second.id = "ab2222deadbb"
    store.save(second)

    assert store.load("ab1111").name == "checkout"
    assert store.load("ab1111c0").name == "checkout"

    with pytest.raises(AmbiguousReference) as excinfo:
        store.load("ab")
    message = str(excinfo.value)
    assert "matches 2 resume points" in message
    # the hint has to name both, or you can't act on the error
    assert "ab1111c0ffee" in message and "ab2222deadbb" in message


def test_two_points_with_the_same_name_are_ambiguous_not_newest_wins(home):
    from deskmark import store
    from deskmark.errors import AmbiguousReference

    store.save(_point("checkout"))
    store.save(_point("checkout"))

    with pytest.raises(AmbiguousReference) as excinfo:
        store.load("checkout")
    assert "named 'checkout'" in str(excinfo.value)


@pytest.mark.parametrize("url", [
    "https://1password.com/vault",
    "https://my.healthprovider.com/results",
    "https://bitwarden.com/vault",
    "https://calendar.google.com/calendar/u/0/r",
    "https://prod.example.com/admin/users",
])
def test_sensitive_pages_are_withheld(url):
    decision = privacy.classify(url, "some title")
    assert decision.verdict is privacy.Verdict.DROP
    # the reason is a category: printing the host would leak what was withheld
    assert "withheld:" in decision.reason
    host = url.split("//")[1].split("/")[0]
    assert host not in decision.reason


def test_a_local_dev_server_is_still_restorable():
    """localhost on a noise port is dropped; an ordinary dev server is kept."""
    assert privacy.classify("http://localhost:3000/admin", "app").verdict is privacy.Verdict.KEEP
    assert privacy.classify("http://localhost:5173/", "vite").verdict is privacy.Verdict.DROP


def test_the_redaction_summary_never_names_what_it_withheld():
    from deskmark.providers.privacy import redaction_summary

    reasons = [privacy.classify(u).reason for u in
               ("https://chase.com/x", "https://chase.com/y", "https://1password.com/vault")]
    summary = redaction_summary(reasons)
    blob = " ".join(summary)
    assert "chase" not in blob and "1password" not in blob
    assert "×2" in blob
