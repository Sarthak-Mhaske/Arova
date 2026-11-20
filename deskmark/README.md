<div align="center">

# Deskmark

**Resume Points for Your Whole Desk**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Platforms](https://img.shields.io/badge/Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](#platform-support)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-6E56CF)](docs/spec.md)
[![Pixels](https://img.shields.io/badge/pixels%20captured-0-success)](#privacy)
[![Version](https://img.shields.io/badge/Version-0.3.0-green.svg)](../../releases)

One command records where your work is — repo, branch, dirty files, open files,
shells, agents, tabs, and the one line that says why. One command puts it back.

No screen recording. No daemon. No account. No network. A resume point is 2–4 KB
of structured JSON, and it is yours.

[Installation](#installation) · [Commands](#available-commands) · [Configuration](#configuration) · [MCP](#agents-mcp) · [Roadmap](#roadmap)

---

**Also known as:** `resume point` · `work state snapshot` · `workspace restore` · `desk state`

</div>

---

## Overview

Deskmark records the state of work in flight — the thing that is normally lost
the moment you close a terminal or switch tasks. It is built for people who work
in ten places at once and for agents that need to know where the work actually
was.

```console
$ deskmark save checkout-idempotency
✓ resume point checkout-idempotency  2.0 KB · zero pixels
  repo    acme-api@feat/checkout (3 changed)
  held    4 files · 2 shells · 1 agent · 6 tabs
  why     make retries idempotent (from branch)
  next    replay the webhook twice
  saved   ~/.deskmark/points/2d3689204957.json
```

The point is small, readable, diffable, and specified in
[docs/spec.md](docs/spec.md). Nothing in it needs Deskmark to be read.

---

## Demo

### Restore the whole desk

`deskmark resume` prints the plan and opens nothing until you say so:

```console
$ deskmark resume
Restore plan for "checkout-idempotency" (5 actions)
  ▣ folder   /home/me/acme/api
  ▤ file     /home/me/acme/api/app/checkout.py
  ▸ terminal /home/me/acme/api   -> cd /home/me/acme/api
  ◈ url      github.com/acme/api/pull/412
  ✦ hint     claude: claude --resume 8f2c1e4a-77b3-4c19-9f11-2b6d5a0c3e77
  recorded commands are shown above but never executed.

dry run — nothing was opened. Re-run with --yes to restore.
```

### Hand it to an agent

```console
$ deskmark packet
<!-- deskmark/v1 id=2d3689204957 name='checkout-idempotency' -->
# Resume point: checkout-idempotency
captured 4m ago · fresh · 2072 bytes · zero pixels captured

## Where you were
repo    acme-api  (/home/me/acme/api)
branch  feat/checkout-idempotency  head 4c1e0a9
state   3 changed · app/checkout.py, tests/test_checkout.py, README.md

## Why / next
why     make retries idempotent (from branch)
next    replay the webhook twice

## Open questions
- tests/test_checkout.py: backfill duplicate-delivery test before enabling retries
```

### Run it yourself

A throwaway "developer machine" in `/tmp` — a repo, a fake session log, a fake
agent, a browser profile — with nothing touched outside `/tmp`:

```bash
./scripts/demo.sh
```

There are no GIFs in this README yet. [docs/demo.tape](docs/demo.tape) renders
them with [VHS](https://github.com/charmbracelet/vhs); if you record one, the
transcripts above are the scenes.

---

**The privacy approach:**

- **Local:** repositories, shells, agents, browser history, and the store
- **Cloud:** nothing, unless you invoke `deskmark look` with your own API key

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│   git    │ ──▶ │  shells  │ ──▶ │  agents  │ ──▶ │  tabs    │
│ (ground) │     │ (hook +  │     │ (process │     │ (history │
│          │     │  /proc)  │     │  scan)   │     │  db)     │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                         │
┌──────────┐     ┌──────────┐     ┌──────────┐         ▼
│  agent   │ ◀── │  packet  │ ◀── │  point   │ ◀─────────────
│  or you  │     │  (text)  │     │  (json)  │
└──────────┘     └──────────┘     └──────────┘
```

> **Privacy:** no screenshots, no keystrokes, no window titles, no file contents,
> no telemetry, and no network call anywhere in the product. Sensitive hosts and
> credential-shaped commands are dropped before the file is written.

---

> **⚠️ Status Notice**
> This is pre-1.0. Linux is the measured platform for restore fidelity; macOS is
> close behind and Windows is best-effort. See [Platform support](#platform-support).
>
> **Not on PyPI yet.** Until v0.4, install from a clone with `pipx install .`.
> Do not `pip install deskmark` — nothing is published under that name.

---

## Privacy

The only claim that matters, and how it is enforced:

- **Nothing is uploaded.** No telemetry, no analytics, no update check, no crash
  reporting. `deskmark look` is the single exception: one shot, opt-in, per
  invocation, to the provider whose key you set.
- **Nothing visual is captured.** No screenshots, no OCR, no window titles, no
  keystrokes. Restoring *opens* things; it never synthesises input.
- **Filtering is on host and path, never on free text.** A filter that matched
  the word "checkout" inside a pull request title would silently delete real
  work, so it does not exist. See
  [`providers/privacy.py`](deskmark/providers/privacy.py).
- **Credentials never enter a point.** Command text that looks like a secret is
  redacted before the write, and the redaction is counted.
- **Recorded commands are context, not instructions.** Restore displays them.
  It never executes them.
- **Uninstall is honest.** Delete `~/.deskmark` and Deskmark has no memory of
  you. That is the whole uninstall.

Full threat model and reporting: [SECURITY.md](SECURITY.md).

---

## Features

### What is captured

| Component | Source | Runs Locally |
|-----------|--------|:------------:|
| Repo, branch, changed files | `git` | ✓ |
| Shells and last failure | shell hook + `/proc` | ✓ |
| Coding agents and session ids | process scan + `~/.claude` | ✓ |
| Browser tabs (host + path) | Chrome/Chromium/Brave/Edge/Firefox databases | ✓ |
| Intent (why / next) | branch, last commit, last command, TODOs | ✓ |
| Vision (`deskmark look`) | your key, your provider | ✗ |

### Five MCP tools, one resource

`resume_latest` · `resume_points_list` · `resume_point_get` · `resume_point_save` ·
`resume_point_plan`, plus `deskmark://resume/<id>` as a markdown resource. The
server answers both `2025-06-18` and `2026-07-28` protocol revisions.

### Restore, not replay

Restore opens a folder, the files you had open, the tabs you were reading, a
terminal per shell directory, and prints the agent commands as hints. It never
executes a recorded command and never synthesises input.

### Zero dependencies

Standard library only, ~3,650 lines, Python 3.9+. No `requests`, no `click`, no
`pydantic`, no wheel to rot. `deskmark doctor` tells you what your machine can
actually capture before you rely on it.

---

## Requirements

- **OS:** Linux (measured), macOS (close), Windows (best-effort)
- **Python:** 3.9 or newer
- **Git:** for repo state (everything else degrades without it)
- **Browser:** optional, for tabs
- **API key:** only for `deskmark look`

### Dependencies

Nothing to install for the product itself. On Linux these make restore and
`look` better, if you have them:

```bash
# Arch
pacman -S --needed git scrot xdotool
paru -S grimblast-git            # Wayland screenshots

# Debian / Ubuntu
sudo apt install git scrot xdotool

# Optional: the terminal you want restored into
pacman -S --needed kitty wezterm alacritty
```

---

## Installation

### Quick Install

```bash
git clone https://github.com/<your-username>/deskmark.git
cd deskmark
pipx install .                   # or: uv tool install .
deskmark doctor
```

### Manual Setup

<details>
<summary>Click to expand</summary>

**1. Install without pipx**

```bash
python -m pip install --user .    # or: python -m pip install -e . for development
deskmark --version
```

**2. Save a first point**, from inside the repo you are working in:

```bash
cd ~/code/acme/api
deskmark save
deskmark packet | head -20
```

**3. Install the shell hook** so restore knows what last failed where:

```bash
deskmark hooks --dry-run    # show the exact line first
deskmark hooks              # appends one marked block to ~/.bashrc / ~/.zshrc
```

**4. Restore it** — plan first, then for real:

```bash
deskmark resume
deskmark resume --yes
```

**5. Add it to your agent** (see [Agents](#agents-mcp)):

```bash
claude mcp add deskmark -- deskmark mcp
```

</details>

---

## Available Commands

| Category | Commands |
|----------|----------|
| **Capture** | `save [name]` · `save -n "why" --next "what's next"` · `save --no-browser --no-agents` |
| **Restore** | `resume` (dry run) · `resume --yes` · `resume --core-only` · `resume --no-tabs` |
| **Inspect** | `list` · `list --fresh` · `show [ref]` · `packet [ref] --budget 1200` · `show --json` |
| **Agents** | `mcp` |
| **Setup** | `doctor` · `doctor --look-keys` · `hooks` · `hooks --uninstall` · `gc --days 30` |
| **Screen** | `look` · `look "why is this failing"` · `look --window` · `look --image shot.png` |

A `ref` is a point id, a unique id prefix of at least two characters, or a name.
Ambiguity is an error, not a guess — restoring the wrong desk is worse than an
error message.

---

## Agents (MCP)

Add Deskmark as a stdio MCP server. Claude Code:

```bash
claude mcp add deskmark -- deskmark mcp
```

Anything with an `mcpServers` block (Cursor, Windsurf, VS Code, Zed):

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

The packet is bounded plain text, safe to put in a prompt: repo, working set,
the failed command, open questions, and the single next action. It never
contains file contents.

---

## Configuration

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DESKMARK_HOME` | `~/.deskmark` | Where points, the index and the session log live |
| `DESKMARK_EDITOR` | auto-detect | Editor used by `resume`, e.g. `zed` |
| `DESKMARK_LOOK_MODEL` | per provider | Model override for `look` |
| `GEMINI_API_KEY` | — | Vision key (cheapest), provider `gemini` |
| `OPENAI_API_KEY` | — | Vision key, provider `openai` |
| `ANTHROPIC_API_KEY` | — | Vision key, provider `anthropic` |

There is no config file. One variable (`DESKMARK_HOME`) moves everything, so the
store and the session log can never disagree about where they are.

### Files

```
~/.deskmark/
├── points/
│   └── 2d3689204957.json         one file per resume point
├── index.json                    a cache: rebuilt from the files above
├── session_log.jsonl             only if `deskmark hooks` was run
└── shell_hook.sh                 only if `deskmark hooks` was run
```

### Restore behaviour

| Setting | Default | Meaning |
|---------|---------|---------|
| Dry run | on | `resume` prints the plan; `--yes` opens it |
| Files | on | `--no-files` skips them |
| Tabs | on | `--no-tabs` skips them |
| Terminals | on | `--no-shells` skips them |
| Recorded commands | never executed | shown in the plan, always |
| History window | 12 h | `save --window 6` narrows it |
| Retention | 200 points / 30 d | `gc` applies both |

Full reference: [docs/config.md](docs/config.md).

---

## Architecture

```
DESKMARK
├── schema.py     # deskmark/v1 dataclasses, validation, digest
├── store.py      # points, index-as-cache, gc
├── capture.py    # builds one point from the providers
├── intent.py     # infers why / next, and says where it came from
├── packet.py     # bounded text + json rendering for agents
├── restore.py    # plan (pure) -> apply (opt-in)
├── mcp.py        # stdio MCP server
├── cli.py        # the human surface
└── providers/
    ├── repo.py       # git ground truth
    ├── terminal.py   # shell hook + /proc
    ├── agents.py     # agents and resumable session ids
    ├── history.py    # browser history, copied then read
    └── privacy.py    # host + path rules. the important one
```

There is no daemon and no server: every command starts, does one thing, and
exits. Why that trade was made, and the invariants that follow from it, are in
[docs/architecture.md](docs/architecture.md).

---

## Platform support

| | Linux | macOS | Windows |
|---|---|---|---|
| Repo, working set, open questions | ✓ | ✓ | ✓ |
| Editor and files | ✓ | ✓ | ✓ |
| Shells and last failure | ✓ hook + `/proc` | hook | hook |
| Agents and session ids | ✓ | — | — |
| Browser tabs | ✓ | ✓ | ✓ |
| `look` screenshots | ✓ grim / scrot / import | ✓ screencapture | ✓ PowerShell |
| Restore fidelity | measured | untested | untested |

When a restore step cannot be performed, the plan says so instead of failing
halfway through. That is the whole reason the table above is honest.

---

## Troubleshooting

<details>
<summary><b>Nothing was captured</b></summary>

```bash
deskmark doctor                     # what this machine can see
deskmark save --json | head -40     # what the point actually contains
```

Outside a git repository, `repo` is `null` and capture says so. That is the
usual cause.
</details>

<details>
<summary><b>No tabs in my point</b></summary>

```bash
deskmark doctor | grep browser
```

No profile found means the browser is somewhere unexpected, or the profile has
never been opened. Tabs are also dropped by policy: mail, banks, auth, health
and password managers are withheld, and the count of withheld pages is reported
without the URLs.
</details>

<details>
<summary><b>Shells have no last command</b></summary>

```bash
deskmark hooks --dry-run
deskmark hooks
# open a new shell, run one failing command, then:
deskmark save shell-test
```

Without the hook, only live shell directories are captured — the command and
exit code come from `session_log.jsonl`.
</details>

<details>
<summary><b><code>look</code> says no screenshot tool</b></summary>

```bash
deskmark doctor --look-keys
```

The error names every tool it tried and the one line that fixes it:
`pacman -S scrot` (X11), `paru -S grimblast-git` (Wayland), or Pillow for a
Python-only path.
</details>

<details>
<summary><b><code>look</code> says no vision provider</b></summary>

```bash
export GEMINI_API_KEY=your-key      # cheapest, ~$0.0015 per look
deskmark look "what is this"
```

`OPENAI_API_KEY` and `ANTHROPIC_API_KEY` work as well. `deskmark look` is the
only part of Deskmark that makes a network call.
</details>

**Common fixes:**

| Problem | Solution |
|---------|----------|
| `ambiguous reference` | Use more of the id (`deskmark list` shows it) or the point's name |
| Point is stale | Restore still works; freshness is a hint, not a gate |
| Corrupt `index.json` | Delete it — it is a cache and rebuilds from `points/` |
| Restore opened the wrong editor | `export DESKMARK_EDITOR=zed` |
| Points piling up | `deskmark gc --days 30 --max 200` |

---

## Roadmap

### v0.3 (Current)

- [x] `deskmark/v1` format with a digest and a conformance document
- [x] `save` / `resume` / `list` / `show` / `packet` / `gc`
- [x] MCP server, both protocol revisions, one markdown resource
- [x] Shell hook, installed and removed between markers
- [x] `look` — one screenshot, one question, your own key
- [x] 67 tests, zero runtime dependencies
- [ ] PyPI release — `pipx install deskmark`

### v0.4 (Next)

- [ ] Restore fidelity measured on five real Linux setups, end to end
- [ ] `resume --check`: report exactly which actions could not be restored
- [ ] Recorded errors for every restore step, not just failures at spawn

> **Kill criterion:** below 80% of plan actions succeeding on an ordinary
> VS Code + iTerm + Chrome desk means the premise is wrong and this stops.

### v0.5 (After that)

- [ ] MCP registry, Claude plugin directory, AUR
- [ ] A second implementation of `deskmark/v1` passing `docs/conformance.md`
- [ ] `deskmark diff <ref> <ref>` — what changed between two points

### v1.0 (Planned)

- [ ] Rust implementation with the same CLI surface and the same tests
- [ ] No Python required on the machine

### Provider Support

| Provider | Status |
|----------|--------|
| VS Code, Cursor, Zed, Sublime, Windsurf | ✓ Supported |
| kitty, WezTerm, Alacritty, Ghostty, GNOME Terminal, Konsole | ✓ Supported |
| Chrome, Chromium, Brave, Edge, Firefox | ✓ Supported |
| Claude Code, Codex, Cursor, opencode, aider, Gemini CLI | ✓ Supported |
| JetBrains editors | Not yet |
| Safari, Arc | Not yet |
| tmux panes (per-pane cwd) | Not yet |

> Providers are one function plus one test. Adding one is the easiest useful
> contribution to this repo — see [docs/testing.md](docs/testing.md).

---

## File Structure

```
deskmark/
├── deskmark/                 # the package
│   ├── schema.py store.py    # format, and where points live
│   ├── capture.py intent.py  # what is happening, and why
│   ├── packet.py restore.py  # agent packet, plan, apply
│   ├── mcp.py cli.py         # the two surfaces
│   ├── providers/            # repo, terminals, agents, history, privacy
│   ├── look/                 # one screenshot, on request
│   └── hooks/shell_hook.sh   # optional shell hook
├── tests/                    # 67 tests: promises, not coverage
├── docs/                     # spec, conformance, architecture, providers,
│                             # config, structure, testing, demo.tape
├── packaging/                # AUR PKGBUILD + release checklist
├── scripts/demo.sh           # throwaway demo machine in /tmp
└── .github/workflows/        # ci.yml, release.yml
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [docs/spec.md](docs/spec.md) | The `deskmark/v1` format, field by field |
| [docs/conformance.md](docs/conformance.md) | Rules any other implementation must pass |
| [docs/architecture.md](docs/architecture.md) | Modules, data flow, invariants |
| [docs/providers.md](docs/providers.md) | What is detected, per tool |
| [docs/config.md](docs/config.md) | Every flag, variable and file |
| [docs/structure.md](docs/structure.md) | Repository layout and conventions |
| [docs/testing.md](docs/testing.md) | What the tests pin, and how to add a provider |
| [AGENTS.md](AGENTS.md) | Instructions for a coding agent working here |

---

## Contributing

```bash
git clone https://github.com/<your-username>/deskmark.git
cd deskmark
python -m pip install -e . && python -m pytest -q    # 67 tests, ~0.6s
git checkout -b feature/your-feature
git commit -m "feat: add your feature"
git push origin feature/your-feature
# Open Pull Request
```

**Commit format:** `type: description`
Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Two rules get a pull request declined regardless of quality: a new runtime
dependency, and anything that captures pixels or keeps a daemon running. See
[CONTRIBUTING.md](CONTRIBUTING.md).

---

## Acknowledgments

### Research

The section on context switching and resumption cost draws on the work of
**Gloria Mark** (UC Irvine) on interruption and task resumption, and on the
observation every developer already knows: the expensive part of a task is
reconstructing where you were.

### Technologies

Built on the standard library, the [Model Context Protocol](https://modelcontextprotocol.io)
for the agent surface, and every tool it reads from the machine — `git`,
`/proc`, browser SQLite databases, and the shells themselves. No screenshots, no
OCR, no computer-use stack.

### Prior art

Restorable-desk tools and session managers exist; none of them expose machine
state an agent can read, which is the gap this fills.

---

## License

Apache-2.0. See [LICENSE](LICENSE).
