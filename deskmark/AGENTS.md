# Instructions for a coding agent

You are working on Deskmark: a Python CLI that records the state of a developer's
desk so it can be restored, or read by an agent over MCP. Standard library only.

Read [docs/architecture.md](docs/architecture.md) before changing capture,
restore or the store. Read [docs/spec.md](docs/spec.md) before touching the
format — it is versioned and other implementations will read it.

## Rules that are not negotiable

1. **No runtime dependencies.** `dependencies = []` in `pyproject.toml` is the
   product. `urllib` instead of `requests`, `sqlite3` instead of an ORM,
   `argparse` instead of `click`. A pull request that adds a dependency needs a
   reason that survives review, and most do not.
2. **Zero pixels.** Nothing may capture screen content, window titles on a
   schedule, OCR text, or keystrokes. `deskmark/look/` is the only code allowed
   to take a screenshot: user-invoked, one shot, never stored.
3. **Never execute a recorded command.** Restore opens things. Commands in a
   point are text. Turning one into a `subprocess` call is a security bug.
4. **No daemon, no server, no background work.** Each command starts, does one
   thing, exits. `deskmark mcp` is a stdio server that lives only as long as its
   client.
5. **Privacy decisions use host and path, never free text.** See
   `deskmark/providers/privacy.py`. Matching titles deletes real work silently.
   When unsure, drop and count the drop.
6. **Degrade, do not raise.** Providers return nothing plus a reason. Only
   `DeskmarkError` subclasses reach the CLI, always with a `hint`.
7. **Errors are one line plus a hint.** No tracebacks in front of a user.

## Commands you will need

```bash
python -m pip install -e . && python -m pytest -q    # 67 tests, ~0.5s
python -m compileall -q deskmark                     # syntax across all modules
python -m build                                      # wheel + sdist in dist/
./scripts/demo.sh                                    # throwaway desk in /tmp
DESKMARK_HOME=/tmp/dm deskmark doctor                # never touch the real home
```

Use `DESKMARK_HOME=/tmp/...` for every manual run. Never write test points into
a real `~/.deskmark`.

## Where things go

| You want to | Touch |
|-------------|-------|
| detect a new editor or terminal | `restore.py` (`GUI_EDITORS`, `TERMINALS`) |
| detect a new agent | `providers/agents.py` (one regex, one test) |
| read a new browser | `providers/history.py` (`candidate_databases`) |
| add a field to a point | `schema.py`, `docs/spec.md`, a round-trip test |
| change restore behaviour | `restore.py` — keep `plan()` pure |
| change the agent surface | `mcp.py`, and the tools table in the README |
| change CLI text | `cli.py` only |

## Before you say it is done

- `python -m pytest -q` passes, and the new promise has a test.
- `deskmark --version`, `doctor`, `save`, `list`, `resume` work from a clean
  `DESKMARK_HOME`.
- No new dependency, no new network call, no new file written outside
  `DESKMARK_HOME`.
- If you changed behaviour, you changed the sentence in the README that
  describes it. Docs that promise more than the code does are a bug.
