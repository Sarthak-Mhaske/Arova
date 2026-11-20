# Changelog

All notable changes to Deskmark will be documented in this file.
The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.1] - 2026-11-20

Audit of every capture path, starting from one visible symptom: `resume`
offered browser pages that had been closed for hours.

### Fixed
- **Tabs came from history, not from the browser.** Chrome keeps a `History` row
  per url for 90 days, so "newest twelve rows" was a list of everything touched
  that afternoon. Tabs are now read from the browser's own session log
  (`Sessions/Session_*` for chrome, brave, edge, chromium, vivaldi and
  `sessionstore-backups/recovery.jsonlz4` for firefox). A tab closed during the
  run carries a close marker and is excluded; the page restored is the entry the
  tab was showing, not the last one stored; a closed browser reports no tabs
  instead of yesterday's. Confidence for the section went 0.75 → 0.9 because it
  is now a fact rather than a guess.
- **Agent detection matched words, not programs.** `python3 serve.py
  ~/claude-notes/x.md` was classified as a claude session, and `-c` was read as
  a session flag, producing `claude --resume import`. Detection is on `argv[0]`
  or the interpreter's script argument (`python3 -m aider`, `node …/claude-code/cli.js`),
  and a session id has to look like one.
- **A failure was attributed to the wrong command.** An output event with no
  command text of its own borrowed the previous line's command, so a command
  that had succeeded was named as the last failure.
- **A git remote url with an embedded token was stored verbatim** and shipped in
  packets. It is redacted now (`https://me:[redacted]@host/x`) and counted, like
  every other credential.
- **`TODO_ITEMS`, `XXXXXXX` and `hackathon` were offered as open questions.** The
  marker now has to be the whole capitalised word, and untracked files are
  scanned too, since that is where new work lives.
- **Renamed files disappeared from the working set**, because git writes the
  status as `old -> new` and the joined string exists nowhere. The new name is
  used.
- **Flatpak browser installs were invisible.** `~/.var/app/<app-id>/…` is
  searched now, for chrome, brave, chromium, edge, vivaldi and firefox.

## [1.0.0] - 2026-11-20

First public release. `deskmark/v1` and the CLI surface are frozen at this
version; anything that changes them gets a major bump.

### Added
- `deskmark save` / `deskmark resume`: capture the state of work in flight
  (repo, branch, dirty files, open editors, shell roots, running agents, recent
  tabs) and put it back, dry run by default.
- `deskmark/v1`: a plain-JSON resume point format with a sha256 digest, an
  explicit `verify()`, and forward-only versioning. See `docs/spec.md`.
- `deskmark mcp`: a stdio MCP server (`resume_latest`, `resume_list`,
  `resume_point_save`, `resume_open_next`, `resume_plan`) that speaks both the
  2025-06-18 and 2026-07-28 protocol eras.
- `deskmark look [question]`: one screenshot, one question, answered with your
  own API key (Gemini, OpenAI or Anthropic). No daemon, no recording, no history.
- `deskmark hooks`: an optional shell hook that records exit codes and the last
  failure in each directory, so "next step" has something real to say.
- `deskmark doctor`: reports what this machine can actually capture.

### Fixed
- **The digest is now checked on every read.** It was computed and stored, and
  then never verified, so a point edited by hand was displayed as if it were the
  truth. A single-reference read refuses it; a listing skips it.
- **`deskmark show <id-prefix>` never worked.** References were matched against
  names only, while the docs promised id prefixes. An ambiguous id prefix, or
  two points sharing a name, now raises a named error and lists the candidates
  instead of quietly returning the newest.
- **`psql postgres://user:hunter2@db/prod` leaked its password.** Redaction only
  looked for keyword shapes like `password=`, so credentials embedded in a URL
  went straight into the point. Redaction now also covers `scheme://user:pass@`,
  Bearer tokens, long flags with a space, and the common token prefixes, and a
  command that carried a secret is now *kept with the secret removed* instead of
  being dropped whole.
- **The privacy summary named what it withheld.** Reasons read
  `sensitive host chase.com ×1`, which defeats the point of dropping the tab.
  Rules are now grouped into categories (`withheld: banking ×1`) and the host is
  never written.
- **Password managers and health hosts were not blocked at all.** 1password,
  bitwarden, dashlane and the like were missing from the list, and
  `my.healthprovider.com` passed because the label rule only matched whole
  labels. Both fixed, with the deliberate over-drop that comes with matching
  inside a label.
- **A non-UTF-8 point file crashed `deskmark list` with a raw traceback.** It is
  now a corrupt-point error: skipped in a listing, reported on a direct read.
- **`DESKMARK_HOME` now decides where **everything** lives. Previously the store
  honoured it while the session log did not, so `capture_from_log` found nothing
  on any machine that set the variable. Pinned by a test.
- `deskmark doctor` recomputed the shell-hook path instead of asking the reader
  for it, so it reported "run `deskmark hooks`" on machines where the hook was
  already installed.
- The installed hook, `hooks/hook_dest()`, and the rc-file block all follow
  `DESKMARK_HOME` now, instead of a hardcoded `~/.deskmark`.
- The shell hook ships inside the wheel (`deskmark/hooks/shell_hook.sh`) instead
  of being resolved out of a legacy source tree, and its stray
  "file watcher verification test" line is gone.
- The store layout lost the vestigial `resume/` level:
  `~/.deskmark/{points/,index.json,session_log.jsonl}`.
- `look` reports one readable line per failed screenshot tool instead of a
  truncated stack of warnings.
- An MCP `resources/read` for a bad uri returns `-32602 unknown resource`
  instead of `-32603 internal error`.
- A failed write to stdout (piped into `head`, or a full disk) no longer prints
  `Exception ignored in ...` on the way out.
- `ResumeError` is now `DeskmarkError`, the name the docs always used.

### Notes
- Zero runtime dependencies. Everything above is standard library only.
- Recorded shell commands are context, never instructions: restore reopens a
  workspace and never replays a command.
- Repository surface: `docs/` (spec, conformance, architecture, providers,
  config, structure, testing), `AGENTS.md`, `SECURITY.md`, AUR packaging under
  `packaging/aur/`, and a tag-triggered `release.yml` that refuses to publish
  when the tag and the package version disagree.

[1.0.1]: https://github.com/<your-username>/deskmark/releases/tag/v1.0.1
[1.0.0]: https://github.com/<your-username>/deskmark/releases/tag/v1.0.0
