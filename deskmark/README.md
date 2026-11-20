# Deskmark

Resume points for your whole desk.

One command saves where your work is — repo, branch, dirty files, the files you
had open, the shells you had rooted somewhere, the agents you had running, the
tabs you were reading, and the one line that says why. One command puts it back.

No screen recording. No daemon. No account. No network. A resume point is 2–4 KB
of structured JSON, and it is yours.

```console
$ deskmark save checkout-idempotency
✓ resume point checkout-idempotency  2.0 KB · zero pixels
  repo    acme-api@feat/checkout (3 changed)
  held    4 files · 2 shells · 1 agent · 6 tabs
  why     make retries idempotent (from branch)
  next    replay the webhook twice
  saved   ~/.deskmark/points/2d3689204957.json

$ deskmark resume
Restore plan for "checkout-idempotency" (5 actions)
  ▣ folder   /home/me/acme/api
  ▤ file     /home/me/acme/api/app/checkout.py
  ▸ terminal /home/me/acme/api   -> cd /home/me/acme/api
  ↗ tab      github.com/acme/api/pull/412
  ⚑ agent    claude --resume 8f2c...   (in /home/me/acme/api)
  recorded commands are shown above but never executed.

$ deskmark resume --yes        # now actually open it
```

**Status:** pre-1.0. Linux is the measured platform; macOS is close behind;
Windows is best-effort. See [Roadmap](#roadmap).

[![CI](https://github.com/<your-username>/deskmark/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-username>/deskmark/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![Dependencies](https://img.shields.io/badge/runtime%20dependencies-0-brightgreen.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-67-brightgreen.svg)](tests/)

---

## Highlights

- **Save the whole desk in one command**, not just one app. Repo, files, shells,
  agents, tabs, intent.
- **Restore is a dry run by default.** You see the plan and the exact actions
  before anything opens. Nothing is ever spawned by accident.
- **Zero pixels.** Structured signals only: paths, branch names, exit codes,
  hosts and paths. No screenshots, no keystrokes, no window titles, no OCR.
- **Zero runtime dependencies.** Standard library only, Python 3.9+, ~3.6k
  lines. It installs in a second and cannot rot.
- **No daemon and no server.** Every command starts, does one thing, and exits.
  There is no background process to babysit and no port to expose.
- **Redaction happens before the file is written.** Sensitive hosts (mail, banks,
  password managers, health, auth) and anything that looks like a credential
  never enter the point. The drop is counted, never the URL.
- **An agent can read it.** `deskmark mcp` is a stdio MCP server, and
  `deskmark packet` prints the same context for anything that speaks
  stdin and stdout.
- **The format is plain JSON** — readable, diffable, committable, and specified
  in [docs/spec.md](docs/spec.md). Nothing here needs Deskmark to be read.

## What a resume point holds

| Part | Example | Source |
|------|---------|--------|
| **repo** | `acme-api@feat/checkout` · head `4c1e0a9` · 3 changed | `git` |
| **files** | `app/checkout.py`, `tests/test_checkout.py`, `README.md` | working set, most specific first |
| **editor** | `code` with 2 files open | process list + editor state |
| **shells** | `/home/me/acme/api` — last command `pytest -k retry`, exit `1` | shell hook log, or `/proc` |
| **agents** | `claude` in `/home/me/acme/api`, resumable | process scan + session files |
| **tabs** | `github.com/acme/api/pull/412`, `docs.stripe.com/api/idempotent` | browser history, host+path filtered |
| **why** | "make retries idempotent" | `--why`, branch, last commit, last command |
| **next** | "replay the webhook twice" | `--next`, or the first TODO in a changed file |

Every part carries a confidence and a time-to-live, because a stale hint is
worse than no hint. Everything degrades quietly: a missing browser, a locked
database, or a non-git directory produces a warning, never a crash.

## Install

Not on PyPI yet — it goes up with v0.4. Until then, from source:

```bash
git clone https://github.com/<your-username>/deskmark.git
cd deskmark
pipx install .          # or: uv tool install .   or: python -m pip install -e .
```

Arch users can build the package in [`packaging/aur`](packaging/aur/PKGBUILD).

## Quick start

1. See what this machine can actually capture:

   ```bash
   deskmark doctor
   ```

2. Save your first resume point, from inside the repo you are working in:

   ```bash
   deskmark save
   ```

3. Look at it as the context an agent would get:

   ```bash
   deskmark packet
   ```

4. Put your desk back — dry run first, then for real:

   ```bash
   deskmark resume
   deskmark resume --yes
   ```

5. Optional, and the only thing that makes restore *specific*: the shell hook.
   It records the last command and the last failure per directory.

   ```bash
   deskmark hooks            # appends one line to ~/.bashrc / ~/.zshrc
   deskmark hooks --dry-run  # show me first
   ```

A throwaway demo machine in `/tmp` (no browser, no agents, no shell hook):

```bash
./scripts/demo.sh
```

## Commands

| Command | What it does |
|---------|--------------|
| `deskmark save [name]` | Capture a resume point of the current work |
| `deskmark resume [ref]` | Show the restore plan; `--yes` actually opens things |
| `deskmark list` | All points, newest first, with age and freshness |
| `deskmark show [ref]` | One point, rendered as a context packet |
| `deskmark packet [ref]` | Just the packet, for piping into an agent |
| `deskmark mcp` | Run the MCP server on stdio |
| `deskmark hooks` | Install or remove the shell hook |
| `deskmark look [question]` | Ask about what is on screen, with your own key |
| `deskmark gc` | Delete old points (`--max 200 --days 30`) |
| `deskmark doctor` | Check what this machine can capture |

```bash
deskmark save checkout -n "why this work exists" --next "the single next action"
deskmark save -C ~/code/other-repo        # capture a different directory
deskmark save --no-browser --no-agents    # minimal point
deskmark resume --no-tabs --core-only     # restore less
deskmark show --json                      # machine-readable
deskmark packet --budget 1200             # token budget, in characters
```

A `ref` is a point id, a unique id prefix, or a name. Ambiguity is an error, not
a guess. Full flag reference: [docs/config.md](docs/config.md).

## Agents (MCP)

Add Deskmark as a stdio MCP server. Claude Code:

```bash
claude mcp add deskmark -- deskmark mcp
```

Anything with an `mcpServers` block (Cursor, Windsurf, VS Code, Zed…):

```json
{
  "mcpServers": {
    "deskmark": { "command": "deskmark", "args": ["mcp"] }
  }
}
```

| Tool | Returns |
|------|---------|
| `resume_latest` | The most recent fresh point as a context packet |
| `resume_points_list` | Points with name, age and freshness |
| `resume_point_get` | One point by ref |
| `resume_point_save` | Capture the current state, from inside the repo |
| `resume_point_plan` | The restore plan — what would open, never opening it |

Resources: `deskmark://resume/<id>` (markdown). The server answers
`2025-06-18` and `2026-07-28` protocol revisions, and `server/discover`
works before you have ever saved a point.

The packet is plain text and bounded, so it is safe to put in a prompt: it
lists the repo, the working set, the failed command, the open questions, and the
single next action. It never contains file contents.

## Looking at your screen (optional)

One screenshot, one question, answered by a model **you** pay, with a key
**you** set. Nothing is stored, nothing is watched, and nothing leaves the
machine unless you type this command.

```bash
deskmark look                        # explain this screen
deskmark look "why is this failing"  # ask about this screen
deskmark look --window "what changed"    # include the focused window name
deskmark look --image shot.png "..."     # ask about a file instead
deskmark look --json                 # provider, model, ms, bytes
```

Keys: `GEMINI_API_KEY` (cheapest, default `gemini-3-flash`), `OPENAI_API_KEY`
(`gpt-5-mini`), or `ANTHROPIC_API_KEY` (`claude-sonnet-4-5`). Roughly
$0.0015 per look on Gemini. If neither a screenshot tool nor a key exists, you
get one line telling you exactly what to install or set —
`deskmark doctor --look-keys` reports both.

## Privacy

The only claim that matters, and how it is enforced:

- **Nothing is uploaded.** No telemetry, no analytics, no update check, no
  crash reporting. `deskmark look` is the single exception, and it is
  one-shot, opt-in, and per invocation.
- **Nothing visual is captured.** No screenshots, no OCR, no window titles, no
  keystrokes. Restoring *opens* things; it never synthesises input.
- **Filtering is on host and path, never on free text.** A filter that matched
  the word "checkout" inside a pull request title would silently delete real
  work — so it does not exist. See
  [`providers/privacy.py`](deskmark/providers/privacy.py).
- **Credentials never enter a point.** Command text that looks like a secret is
  redacted before the write, and the redaction is counted.
- **Recorded commands are context, not instructions.** Restore displays them.
  It never executes them.
- **Uninstall is honest.** Delete `~/.deskmark` and Deskmark has no memory of
  you. That is the whole uninstall.

## Documentation

| Document | Contents |
|----------|----------|
| [docs/spec.md](docs/spec.md) | The `deskmark/v1` format, field by field |
| [docs/conformance.md](docs/conformance.md) | Rules any other implementation must pass |
| [docs/architecture.md](docs/architecture.md) | Modules, data flow, invariants |
| [docs/providers.md](docs/providers.md) | What is detected, per editor, terminal, browser and agent |
| [docs/config.md](docs/config.md) | Every flag, environment variable and file |
| [docs/structure.md](docs/structure.md) | Repository layout |
| [docs/testing.md](docs/testing.md) | How to run and extend the tests |
| [AGENTS.md](AGENTS.md) | Instructions for a coding agent working on this repo |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## Platform support

| | Linux | macOS | Windows |
|---|---|---|---|
| Repo, working set, open questions | ✓ | ✓ | ✓ |
| Editor and files | ✓ | ✓ | ✓ |
| Shells and last failure | ✓ hook + `/proc` | hook | hook |
| Agents | ✓ | ✓ | partial |
| Browser tabs | ✓ | ✓ | ✓ |
| `look` screenshots | ✓ `grim` / `scrot` / `import` | ✓ `screencapture` | ✓ PowerShell |

Linux is where restore fidelity is measured. If a restore step cannot be
performed on your machine, `deskmark resume` says so in the plan instead of
failing halfway through.

## Roadmap

- **v0.4 — restore fidelity on Linux, measured.** Five real setups, each
  restored end to end, with the failures written down. `deskmark resume` reports
  what it could not restore. PyPI release. *Kill criterion: below 80% of plan
  actions succeed on an ordinary VS Code + iTerm + Chrome desk.*
- **v0.5 — the format gets readers.** MCP registry, Claude plugin directory,
  AUR, and the conformance document implemented by something that is not
  Deskmark.
- **v1.0 — the binary.** A Rust implementation of `deskmark/v1` with the same
  CLI surface and the same tests, for machines that do not have Python.

Nothing after v0.4 ships until v0.4 is green.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Two rules: every promise gets a test,
and nothing new may leave the machine.

```bash
python -m pip install -e . && python -m pytest -q   # 67 tests, ~0.5s
```

## License

Apache-2.0. See [LICENSE](LICENSE).
