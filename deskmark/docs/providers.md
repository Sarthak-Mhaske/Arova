# Providers — what is actually detected

Every provider reports what it found, how sure it is, and how long the finding
stays useful. When it finds nothing, it reports *why* — and that reason is what
`deskmark doctor` prints.

| Provider | Module | Confidence | TTL |
|----------|--------|-----------|-----|
| Repo, working set, open questions | `providers/repo.py` | 1.0 | 1 h (questions 7 d) |
| Shells and last failure | `providers/terminal.py` | 0.9 | 6 h |
| Agents | `providers/agents.py` | 0.8 | 6 h |
| Browser tabs | `providers/sessions.py` | 0.9 | 6 h |
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
- Open questions = `TODO` / `FIXME` / `HACK` / `XXX` markers in the working set
  including untracked files, capped, first marker per file. The marker has to be
  the whole word in capitals, so `TODO_ITEMS`, `XXXXXXX` and "hackathon" are
  names and placeholders, not questions. A marker inside a string literal still
  matches; that is the limit of not parsing the language.
- Renames are followed to the new name, so a renamed file is reported once
  instead of vanishing into a `old -> new` string that exists nowhere

No git → `repo: null` and a warning. A dirty tree is recorded as counts plus
paths, never as a patch (a patch would blow the size budget and could contain
secrets).

The remote url is redacted before it is stored: `https://me:ghp_…@github.com/x`
becomes `https://me:[redacted]@github.com/x` and the point records
`remote url credentials ×1`. It is the one field in the repo section where a
token can sit inside a value that looks like a normal url.

## Shells (`providers/terminal.py`)

Two independent sources, because both are partial:

| Source | Gives | Needs |
|--------|-------|-------|
| `shell-hook` | command text, cwd, exit code, duration | `deskmark hooks` |
| `/proc` | live shell cwd | Linux |

The merge prefers log entries (they carry intent) and keeps live shell
directories that have no log entry. Capped at 6 shells.

A command that carries a credential is **kept with the credential removed**, not
dropped: the last failing command is the single most useful line in the whole
point, and deleting it would hide the work along with the secret. Four shapes
are recognised before anything is written:

| Shape | Example becomes |
|-------|-----------------|
| `key=value`, `key: value`, `--key=value` | `export API_KEY=[redacted]` |
| long flags with a space | `docker login --password [redacted]` |
| `scheme://user:password@host` | `psql postgres://user:[redacted]@db/prod` |
| well-known token prefixes | `sk-… ghp_… glpat-… npm_… AKIA… AIza… xox…` |

Short flags are deliberately *not* inferred — `-p` is a port, a print or a
password depending on the program — and a keyword with no value after it
(`grep -rn token src/`) is left alone.

On macOS and Windows only the hook source exists, so install it if you want
shells.

## Agents (`providers/agents.py`)

Scans the process list and decides from the program the process was started as,
not from the words on the command line:

| Agent | Detected as |
|-------|-------------|
| Claude Code | `claude` — with a resumable session id from `~/.claude/projects` |
| Codex | `codex` |
| Cursor | `cursor`, `cursor-agent` |
| opencode | `opencode` |
| aider | `aider` |
| Gemini CLI | `gemini` |

Matching on `argv[0]` is the whole point. A regex over the full line called
`python3 serve.py ~/claude-notes/x.md` a claude session, and any process that
happened to mention `gemini` in a path became an agent. The rules are:

- the executable's basename is an agent name (`claude`, `codex`, `cursor-agent`,
  `opencode`, `aider`, `gemini`, `goose`, `amp`, `openclaw`);
- or the interpreter's first arguments point at an agent: `python3 -m aider`,
  `npx @google/gemini-cli`, `node …/@anthropic-ai/claude-code/cli.js`. Package
  directory names (`claude-code`, `gemini-cli`) are specific enough that a
  project folder will not collide with them.

Session ids come from long flags only (`--resume`, `--session`, `--session-id`,
`--continue`) and have to look like an id: a uuid, or 16+ characters with a
digit. Short flags are ignored on purpose: `-c` means `--continue` to claude and
"run this string" to python, and reading it as a session id produced
`claude --resume import`.

The useful output is not "an agent was running", it is `claude --resume 8f2c…`
in `/home/me/acme/api` — a command you can paste. Capped at 6, one per
(kind, cwd) pair. A process whose cwd cannot be read (another user's) or whose
cwd was deleted is skipped rather than reported with a broken hint. Linux-first:
on other platforms this degrades to nothing.

## Browser tabs (`providers/sessions.py`)

Tabs come from the file the browser itself restores from, not from history.
That distinction is the whole section: chrome keeps a History row per url for
ninety days, so "the newest twelve rows" is a list of everything you touched
this afternoon, closed tabs included. The session log is append-only state,
and closing a tab appends a close marker to it.

| Browser | File read | Profiles |
|---------|-----------|----------|
| Chrome | `Sessions/Session_*` | `~/.config/google-chrome/`, `.../google-chrome-beta/` |
| Chromium | same | `~/.config/chromium/` |
| Brave | same | `~/.config/BraveSoftware/Brave-Browser/` |
| Edge | same | `~/.config/microsoft-edge/` |
| Vivaldi | same | `~/.config/vivaldi/` |
| Firefox | `sessionstore-backups/recovery.jsonlz4` | `~/.mozilla/firefox/*/` |

Flatpak installs are looked for as well (`~/.var/app/<app-id>/…`), and so are
macOS (`~/Library/Application Support/…`) and Windows (`%LOCALAPPDATA%`,
`%APPDATA%`) layouts.

The chromium format is a binary command log, `SNSS` then length-prefixed
records. Three things in it matter here:

- `Session_*` is the current run; `Tabs_*` is the recently **closed** list and
  is never read, because restoring closed tabs is the bug this replaced;
- a tab that has a navigation record and no close marker after it is open, and
  its selected navigation index is the page you were looking at, not the last
  one it happens to have stored;
- files are ranked by the number in the filename, not by mtime, because a
  profile copied out of a backup keeps the name and loses the timestamp.

Firefox writes a JSON document with an lz4 block inside it (`mozLz40\0`, length,
block). `lz4_block()` is a small decoder for that block, verified against the
reference `lz4` implementation on both compression modes.

Everything fails closed. A truncated tail, an unknown version, a record that
decodes to something that is not a URL: that command is dropped, and if nothing
decodes the section is skipped with a reason. Nothing is written back to a
browser file, and a browser that is closed reports no tabs rather than the tabs
you had open yesterday.

Incognito and private windows are never read: they live in separate files which
this does not open.

Pages kept are de-duplicated by URL, capped at 12, ordered work first, and
classified before they are stored:

- **kept** — a page with a host, e.g. a pull request, an issue, a doc page
- **dropped** — non-http schemes (`chrome://newtab`, `file://`), blank pages,
  sensitive hosts, and admin consoles on remote hosts

Sensitive is decided on *host and path*, never on the title, and grouped by
category so the point can say what it withheld without naming it:

| Category | Examples |
|----------|----------|
| `banking` | chase, wells fargo, paypal, stripe dashboard, wise |
| `trading` | zerodha, groww, coinbase, fidelity |
| `identity` | google accounts, okta, auth0, 1password, bitwarden, dashlane |
| `tax-and-government` | irs, incometax.gov.in, passport, mychart |
| `health` | practo, 1mg, cvs, walgreens |
| `webmail` | gmail, outlook, proton, fastmail |
| `calendar` | google calendar, calendly |
| `social` | instagram, x, whatsapp web, discord |

Plus path rules for auth and payment sessions (`/login`, `/oauth`, `/2fa`,
`/billing/portal`, `session_token=`) and a host-label rule that catches domains
carrying words like `bank`, `health`, `wallet`, `insurance` anywhere in the name
(`my.healthprovider.com`). The label rule over-drops — `investopedia.com` goes
with it — because over-dropping costs a research tab and under-dropping leaks a
medical record.

A local dev server is treated as restorable: `localhost:3000/admin` is kept,
while the same `/admin` path on a remote host is withheld, and noise ports
(`5173`, `8765`, `1420`, `3030`) are dropped.

The point records how many were dropped and why — never which URLs were dropped.

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
