# Providers — what is actually detected

Every provider reports what it found, how sure it is, and how long the finding
stays useful. When it finds nothing, it reports *why* — and that reason is what
`deskmark doctor` prints.

| Provider | Module | Confidence | TTL |
|----------|--------|-----------|-----|
| Repo, working set, open questions | `providers/repo.py` | 1.0 | 1 h (questions 7 d) |
| Shells and last failure | `providers/terminal.py` | 0.9 | 6 h |
| Agents | `providers/agents.py` | 0.8 | 6 h |
| Browser tabs | `providers/history.py` | 0.6 | 6 h |
| Window title (`look --window` only) | `look/screen.py` | 0.5 | not stored |

Confidence is not decoration: it is what restore uses to decide whether a hint
is worth acting on, and what a packet prints when a part is faint.

## Repo (`providers/repo.py`)

Source of truth, and the only part of a point that is objectively verifiable.

- `git rev-parse --show-toplevel`, `--abbrev-ref HEAD`, `--short HEAD`
- `git status --porcelain` → changed files, split into staged / unstaged /
  untracked
- `git log -1` → the last commit subject, used for *why*
- Working set = repo root, then changed files, then files an editor had open
  (most specific first), de-duplicated, files that vanished removed
- Open questions = `TODO` / `FIXME` / `XXX` markers in the working set, capped

No git → `repo: null` and a warning. A dirty tree is recorded as counts plus
paths, never as a patch (a patch would blow the size budget and could contain
secrets).

## Shells (`providers/terminal.py`)

Two independent sources, because both are partial:

| Source | Gives | Needs |
|--------|-------|-------|
| `shell-hook` | command text, cwd, exit code, duration | `deskmark hooks` |
| `/proc` | live shell cwd | Linux |

The merge prefers log entries (they carry intent) and keeps live shell
directories that have no log entry. Capped at 6 shells.

Command text that looks like a credential (`sk-…`, `ghp_…`, `AKIA…`, `--password`,
`Bearer …`, `export *_KEY=`) is redacted *before* serialisation. The last failed
command of a directory is the single most useful line in the whole point: it is
what turns "you were in this folder" into "you were fixing this".

On macOS and Windows only the hook source exists, so install it if you want
shells.

## Agents (`providers/agents.py`)

Scans the process list and classifies command lines:

| Agent | Detected as |
|-------|-------------|
| Claude Code | `claude` — with a resumable session id from `~/.claude/projects` |
| Codex | `codex` |
| Cursor | `cursor`, `cursor-agent` |
| opencode | `opencode` |
| aider | `aider` |
| Gemini CLI | `gemini` |

The useful output is not "an agent was running", it is `claude --resume 8f2c…`
in `/home/me/acme/api` — a command you can paste. Capped at 6, one per
(kind, cwd) pair. Linux-first: on other platforms this degrades to nothing.

## Browser tabs (`providers/history.py`)

Reads history databases directly. No extension, no permission prompt, no sync,
no server.

| Browser | Profiles |
|---------|----------|
| Chrome | `~/.config/google-chrome/*/History` |
| Chromium | `~/.config/chromium/*/History` |
| Brave | `~/.config/BraveSoftware/Brave-Browser/*/History` |
| Edge | `~/.config/microsoft-edge/*/History` |
| Firefox | `~/.mozilla/firefox/*/places.sqlite`, `~/.var/app/org.mozilla.firefox/…` |

A running browser holds a lock on its database, so the file is **copied** to a
temp location and read there, then deleted. Tabs newer than the window (default
12 h) are kept, de-duplicated by URL, capped at 12, and each one is classified
before it is stored:

- **kept** — a page with a path, e.g. a pull request, an issue, a doc page
- **downranked** — search result pages, new-tab pages, badge counters
- **dropped** — sensitive hosts, local files, `javascript:`/`data:` URLs, and
  anything unclassifiable

Sensitive means *host and path*, never title: mail, calendar, banks, password
managers, health, auth flows, admin consoles, private-repo paths. If the
classification is uncertain, the tab is dropped. The point records how many were
dropped and why — never which URLs were dropped.

## Editors and terminals (restore side)

`restore.py` opens, in this order:

1. the repo root folder
2. the files that were open
3. the tabs
4. a terminal per recorded shell directory

GUI editors tried, first one found wins: `code`, `cursor`, `zed`, `subl`,
`code-insiders`, `windsurf`, then the platform file manager (`xdg-open`,
`open`, `explorer`). Terminals tried: `kitty`, `wezterm`, `alacritty`,
`ghostty`, `gnome-terminal`, `konsole`, `xterm`, `wt`, `cmux`. Override the
editor with `DESKMARK_EDITOR=zed`.

If no editor is found the plan says `-> file manager (no GUI editor found)`
rather than pretending it will open one.

## Screenshots (`look/screen.py`)

Only for `deskmark look`, only when you ask for it, never stored.

| Platform | Tried in order |
|----------|----------------|
| Linux | Pillow (if installed), `grim`, `grimblast`, `scrot`, `import`, `maim` |
| macOS | `screencapture` |
| Windows | PowerShell + `System.Drawing` |

The focused window name comes from `hyprctl`, `swaymsg`, `xdotool`,
`osascript` or PowerShell. When every tool fails, the error names each attempt
and the one command that would fix it, because "cannot take a screenshot" with
no next step is how tools get uninstalled.
