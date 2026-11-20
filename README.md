<div align="center">

# Arova

**Resume points for your whole desk**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](#requirements)
[![Platforms](https://img.shields.io/badge/Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](#platform-support)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-6E56CF)](docs/RESUME_POINT.md)
[![Pixels captured](https://img.shields.io/badge/pixels%20captured-0-success)](#privacy)
[![Version](https://img.shields.io/badge/Version-0.2.0-green.svg)](https://github.com/Sarthak-Mhaske/Arova/releases)

One command to save where your work is. One to put it back.  
No screen recording, no daemon, no account, no network.

[Installation](#installation) · [Commands](#commands) · [The format](docs/RESUME_POINT.md) · [MCP](#mcp) · [Architecture](#architecture) · [Roadmap](#roadmap)

---

**Also known as:** `resume point` · `work state snapshot` · `workspace restore`  
Looking for the old desktop app from v0.1? It's frozen in [`attic/`](attic/README.md).

</div>

---

## Overview

Git remembers what you committed. Nothing remembers **what you were doing**.

Come back to a project after two days and the thing that costs you an hour isn't the
code — it's that the *reason* for the branch, the tab you were reading, the test that
was failing and the exact next step all lived in your head.

Arova writes that down as a **resume point**: a 3 KB JSON file holding the repo and
branch you were on, the files in flight, the tabs you were reading, the folders your
shells were in, the AI agents you had running, and one line each for *why* and
*what's next*. Then it puts the desk back on request — or hands the file to your agent.

---

## Demo

### Resume: the whole point

Close everything. Come back tomorrow.

```console
$ arova save checkout-idempotency
✓ resume point checkout-idempotency  3.6 KB · zero pixels
  repo    api@feat/checkout-idempotency (1 modified, 1 new)
  held    3 files · 3 tabs · 1 shell · agents claude
  why     working on "checkout idempotency" (1 file changed, 2 insertions(+))
  next    src/webhooks/handler.py:3 — TODO: backfill duplicate-delivery test
  saved   ~/.arova/resume/points/2d3689204957.json
```

```console
$ arova resume
Restore plan for "checkout-idempotency" (8 actions)
  ▣ folder   /code/acme/api   -> code (editor)
  ▤ file     src/webhooks/handler.py
  ▤ file     src/webhooks/idempotency.py
  ◈ url      https://github.com/acme/api/pull/412  -- Add checkout idempotency · PR #412
  ◈ url      https://stripe.com/docs/webhooks/best-practices
  ▸ terminal /code/acme/api
  ✦ hint     claude: claude --resume 8f2c1e4a-77b3-4c19-9f11-2b6d5a0c3e77
  recorded commands are shown above but never executed.

dry run — nothing was opened. Re-run with --yes to restore.
```

### Your agent keeps the thread too

An agent that can read a resume point stops asking you to re-explain the project.

```console
$ claude   # ... later, after context compaction
> what was I doing?

  [arova · resume_latest]
  Resume point: checkout-idempotency — captured 2h ago · fresh
  branch  feat/checkout-idempotency
  next    src/webhooks/handler.py:3 — TODO: backfill duplicate-delivery test
  reading https://stripe.com/docs/webhooks/best-practices
  agents  claude in /code/acme/api
```

The agent can save one too, before it forgets everything.

### Reproducible

The terminal demos come from `scripts/demo.sh`, which builds a throwaway "developer
machine" in `/tmp/arova-demo` and never touches your real home directory. GIFs are
rendered from `docs/demo.tape` with [VHS](https://github.com/charmbracelet/vhs):

```bash
./scripts/demo.sh          # see it run, now
vhs docs/demo.tape         # render assets/demo.gif
```

---

## How it works

**Structured signals in, a small file out.** Arova asks the things your OS already
knows instead of recording your screen.

```
┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
│ git state  │   │  browser   │   │ shell hook │   │  agent     │
│ branch,    │   │  history   │   │ + /proc    │   │ processes  │
│ dirty set  │   │ (7 kinds) │   │ cwd, exit  │   │ + sessions │
└─────┬──────┘   └─────┬──────┘   └─────┬──────┘   └─────┬──────┘
      │                │                │                │
      └────────────────┴───────┬────────┴────────────────┘
                                ▼
                    ┌───────────────────────┐
                    │   privacy policy      │  host + path only,
                    │   (counted drops)     │  never free-text titles
                    └───────────┬───────────┘
                                ▼
                    ┌───────────────────────┐
                    │  arova.resume/v1      │  3 KB JSON, digest,
                    │  ResumePoint          │  provenance, TTL
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ arova resume  │      │ arova packet  │      │  arova mcp    │
│ reopen desk   │      │ agent context │      │ tools + res.  │
└───────────────┘      └───────────────┘      └───────────────┘
```

> **Zero pixels.** Arova never captures a screenshot, never starts a microphone, never
> opens a socket. There is no image to leak and no video to subpoena. Monthly storage is
> measured in megabytes, not tens of gigabytes.

---

> **⚠️ Early software notice**
>
> v0.2 is the primitive, not the product. `save`, `resume`, `packet` and `mcp` are
> tested (35 tests). Restore adapters are best on Linux, good on macOS, and use the OS
> opener on Windows. The UI, the editor extension and cross-machine resume are on the
> [roadmap](#roadmap) — they are not in this release.

---

## Features

### What it captures

| Signal | Source | Leaves your machine |
|--------|--------|:-------------------:|
| Repo, branch, head, dirty set, diffstat, recent commits | `git` | ✗ never |
| Files and folders in the working set, ranked by reason | git + filesystem | ✗ never |
| Tabs you were reading | browser history DBs (7 browsers), read-only copy | ✗ never |
| Shell roots, last command, **last failure and exit code** | shell hook + `/proc` | ✗ never |
| Running AI agents and their session ids | `/proc` + agent session files | ✗ never |
| `why` and `next_step` | derived deterministically from the above | ✗ never |

### What it deliberately does not do

- ❌ Screenshots, OCR, screen video, audio
- ❌ Network calls of any kind (no telemetry, no sync, no update check)
- ❌ Running recorded commands on restore
- ❌ A background daemon
- ❌ A database (a resume point is a file)

### Privacy

Filtering happens **before anything touches disk**, and it is decided on host and path —
never on free-text titles. (An earlier version matched the word "checkout" inside a pull
request title and silently deleted real work. That bug is now a test.)

Dropped by default: banking and payments, identity providers and sign-in flows, health,
tax and government, webmail, social and chat, local dev UI, blank pages.

Every drop is **counted** and written into the point, so you can see what was withheld
instead of assuming the tool saw everything:

```json
"redactions": ["sensitive host mail.google.com ×1", "sensitive host chase.com ×2"]
```

---

## Requirements

- **Python** 3.9 or newer (tested on 3.11) — no third-party packages
- **git** (optional, for repo state)
- **An editor CLI** (optional, for restore): `code`, `cursor`, `zed`, `subl`
- **A terminal** (optional, for restore): kitty, wezterm, alacritty, ghostty, gnome-terminal, konsole, xterm

Works on Linux, macOS and Windows.

---

## Installation

### Quick install

Not on PyPI yet — v0.2 installs from source, in one step:

```bash
git clone https://github.com/Sarthak-Mhaske/Arova.git && cd Arova
python -m pip install -e .        # or: pipx install -e .
arova doctor                      # what can this machine capture?
```

> `pipx install arova` and a single static binary arrive with v1.0 (see [Roadmap](#roadmap)).

### Manual setup

<details>
<summary>Click to expand</summary>

**1. From source**

```bash
git clone https://github.com/Sarthak-Mhaske/Arova.git
cd Arova
python -m pip install -e .
```

**2. Try it without touching your real home**

```bash
./scripts/demo.sh            # builds /tmp/arova-demo and runs save + packet + resume
```

**3. Optional: install the shell hook**

Without it, Arova still sees live shells and git state. With it, it also knows what last
failed and where — which is what makes the "next" line useful.

```bash
arova hooks                  # adds one marked block to ~/.zshrc or ~/.bashrc
arova hooks --uninstall      # removes exactly that block
```

</details>

---

## Commands

| Command | What it does |
|---------|--------------|
| `arova save [name]` | Capture a resume point of the current work (name optional) |
| `arova resume [ref]` | Show the restore plan; `--yes` actually opens things |
| `arova list` | All resume points, newest first, with age and staleness |
| `arova show [ref]` | One point as a context packet |
| `arova packet [ref]` | Just the packet, for piping into an agent |
| `arova mcp` | Run the MCP server on stdio |
| `arova doctor` | Check what this machine can capture |
| `arova hooks` | Install or remove the shell hook |
| `arova gc` | Delete old points (`--max 200 --days 30`) |

Useful flags:

```bash
arova save checkout -n "why this work exists" --next "the single next action"
arova save -C ~/code/other-repo        # capture a different directory
arova save --no-browser --no-agents    # minimal point
arova resume --no-tabs --core-only     # restore less
arova show --json                      # machine-readable
arova packet --budget 1200             # token budget, in characters
```

---

## Looking at your screen

`arova save` never touches the pixels. When you *want* eyes, there is one
command for it:

```bash
arova look                                  # what am I looking at?
arova look "why is this test failing"       # ask about this screen
arova look --window "what changed here"     # include the focused window's name
arova look --image shot.png "explain this"  # ask about a file instead
```

It takes **one** screenshot, sends it to the provider you configured, prints
the answer, and exits. There is no daemon, no recording, no history of what you
looked at, and no default account. Bring a key:

```bash
export GEMINI_API_KEY=...      # cheapest vision per image (~$0.001)
# or OPENAI_API_KEY / ANTHROPIC_API_KEY
```

Capture works with whatever the machine has — Pillow if installed, otherwise
`grim` on wlroots/Wayland, `scrot` on X11, `screencapture` on macOS, PowerShell
on Windows. If none is available, `arova look` tells you exactly what to install
and takes nothing.

## MCP

```json
{
  "mcpServers": {
    "arova": { "command": "arova", "args": ["mcp"] }
  }
}
```

| Tool | Purpose |
|------|---------|
| `resume_latest` | Read the newest point as a context packet |
| `resume_point_save` | Checkpoint the current state before context is lost |
| `resume_points_list` | List points with age and staleness |
| `resume_point_get` | One point, as a packet or raw JSON |
| `resume_point_plan` | What a restore *would* open — read-only |

Resources: `arova://resume/<id>`.

Speaks **both** MCP eras: the stateless `server/discover` call from the 2026-07-28
revision and the legacy `initialize` handshake, so it works with current and older
clients alike.

---

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `AROVA_HOME` | `~/.arova` | Where points are stored |
| `AROVA_EDITOR` | auto-detect | Editor command used by restore, e.g. `cursor` |
| `XDG_DATA_HOME` | `~/.local/share` | Where the shell hook writes its log |

Everything lives under `~/.arova/`:

```
~/.arova/
├── resume/
│   ├── points/
│   │   └── 2d3689204957.json     # one file per resume point
│   └── index.json                # list + summaries
└── shell_hook.sh                 # if `arova hooks` was run
```

> **Uninstall:** delete `~/.arova` and Arova has no memory of you. That is the whole uninstall.

---

## Architecture

```
AROVA
├── cli.py          # save · resume · list · show · packet · mcp · doctor · hooks · gc
├── capture.py      # assemble a point; every provider may fail, none may crash
├── schema.py       # arova.resume/v1: provenance, TTL, digest, validation
├── intent.py       # deterministic why / next_step, each tagged with its source
├── packet.py       # token-budgeted context packet for agents
├── restore.py      # plan -> dry run -> apply; never executes a command
├── store.py        # files, not a database; atomic writes
├── mcp.py          # dual-era MCP server over stdio
└── providers/
    ├── repo.py     # git state, working set, TODO markers
    ├── history.py  # browser history across 5 browsers, no extension
    ├── privacy.py  # host-and-path policy with counted redactions
    ├── terminal.py # shell hook log + /proc
    └── agents.py   # running agents + recovered session ids
```

**Zero runtime dependencies.** Standard library only. The format is language-agnostic
JSON, so another implementation can read and write it without Arova — that is the point
of a format.

---

## Troubleshooting

<details>
<summary><b>No tabs captured</b></summary>

Arova reads history databases directly, so it needs at least one browser profile it
recognises (Chrome, Chromium, Brave, Edge, Vivaldi, Arc, Firefox).

```bash
arova doctor                     # shows profile count and policy drops
arova save test --window 168     # widen the window to 7 days
```
</details>

<details>
<summary><b>No agents detected</b></summary>

Agents are found by scanning `/proc` (Linux) for known command lines. On macOS and
Windows this provider is currently a no-op.

```bash
arova doctor                     # check the "claude sessions" line
```
</details>

<details>
<summary><b>Resume opens nothing</b></summary>

Restore is a dry run unless you pass `--yes`, and it needs a way to open things.

```bash
arova resume --yes
export AROVA_EDITOR=cursor       # if no editor was auto-detected
```
</details>

<details>
<summary><b>A path is marked "missing"</b></summary>

The point came from a directory that no longer exists — usually a different machine.
Restore skips those instead of failing.

```bash
arova resume --json | grep missing
```
</details>

**Common fixes:**

| Problem | Solution |
|---------|----------|
| `command not found: arova` | Add `~/.local/bin` to `PATH` (pipx) |
| Empty `why` / `next` | `arova save name --next "..."`, or leave a TODO in a changed file |
| Tabs feel wrong | `--no-browser`, or widen `--window` |
| Point says STALE | Older than its TTL (7 days); verify before trusting it |
| Nothing captured at all | `arova doctor`, and check you're inside a directory with files |

---

## Roadmap

### v0.2 — the primitive (current)

- [x] `arova.resume/v1` format + [spec](docs/RESUME_POINT.md)
- [x] CLI: save / resume / list / show / packet / mcp / doctor / hooks / gc
- [x] Dual-era MCP server
- [x] Privacy policy on host + path, with counted redactions
- [x] Zero dependencies, 35 tests, Apache-2.0

### v0.3 — the surfaces

- [ ] `arova ui` — the resume gallery and selective restore, in the browser
- [ ] VS Code / Cursor extension: real open editors and unsaved state
- [ ] `arova diff <a> <b>` — what changed between two points
- [ ] Auto-checkpoint hooks for Claude Code / Codex / Cursor

### v1.0 — the binary

- [ ] **Rewrite the core in Rust**: one static binary, no Python runtime
- [ ] `brew install arova` · `cargo install arova` · `curl | sh`
- [ ] Desktop shell (Tauri) around the same UI
- [ ] Cross-machine resume: a point committed to a repo resumes on another laptop

### Platform support

| Platform | Capture | Restore | Notes |
|----------|:-------:|:-------:|-------|
| Linux | ✓ | ✓ | Primary target. All providers available. |
| macOS | ◐ | ✓ | git, browser history and the shell hook work; `/proc` providers (live shells, agents) are Linux-only. |
| Windows | ◐ | ◐ | git and browser history work. Restore opens via the OS; terminal adapters are partial. |

### Provider support

| Provider | Status |
|----------|:-------|
| git state, working set, TODOs | ✓ |
| Chrome / Chromium / Brave / Edge / Vivaldi / Arc / Firefox | ✓ |
| Shell hook + `/proc` shells | ✓ |
| Claude Code, Codex, Cursor, OpenCode, OpenClaw, Aider, Gemini, Goose, Amp | ✓ |
| Terminal, Zed, JetBrains, Sublime (installed-app restore) | ✓ |
| macOS Spaces, Windows virtual desktops, tmux layouts | Planned (v0.4) |

---

## File structure

```
Arova/
├── arova/
│   ├── resume/              # the product: format, capture, restore, MCP, CLI
│   └── core/platform/       # cross-platform catalog + launcher (from v0.1)
├── docs/
│   ├── RESUME_POINT.md      # the format specification
│   └── demo.tape            # VHS script that renders the demo GIF
├── scripts/demo.sh          # throwaway demo machine in /tmp
├── tests/                   # 35 tests: promises, not coverage
├── attic/                   # frozen v0.1 desktop app (see attic/README.md)
├── PIVOT.md                 # why this product, and what it replaced
└── frontend/                # v0.1 UI — being rewired for `arova ui` in v0.3
```

---

## Contributing

```bash
git clone https://github.com/YOUR_USERNAME/Arova.git
git checkout -b feature/your-feature
# make changes, add a test
git commit -m "feat: add your feature"
git push origin feature/your-feature
# open a Pull Request
```

**Commit format:** `type: description`  
Types: `feat`, `fix`, `docs`, `refactor`, `chore`

Before you open a PR, read the four rules in [CONTRIBUTING.md](CONTRIBUTING.md). The
short version: zero pixels, resume not search, never execute recorded commands, say what
is missing.

---

## Acknowledgments

Arova v0.2 is built on the surviving parts of **Arova v0.1**, a desktop cognitive-runtime
experiment. Its cross-platform application catalog (`arova/core/platform/`) and its
privacy-first shell hook were too good to throw away, so they weren't.

The context-switching research referenced in [`PIVOT.md`](PIVOT.md) is by Gloria Mark and
colleagues at UC Irvine.

## License

[Apache-2.0](LICENSE). The format is meant to be implemented by other tools — this
repository should be the reference implementation, not the only option.
