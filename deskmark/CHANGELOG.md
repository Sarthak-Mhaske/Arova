# Changelog

All notable changes to Deskmark will be documented in this file.
The format is [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-11-20

First release under this name. Earlier iterations existed under a different
name and were never published.

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
- `DESKMARK_HOME` now decides where **everything** lives. Previously the store
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

### Notes
- Zero runtime dependencies. Everything above is standard library only.
- Recorded shell commands are context, never instructions: restore reopens a
  workspace and never replays a command.
- Repository surface: `docs/` (spec, conformance, architecture, providers,
  config, structure, testing), `AGENTS.md`, `SECURITY.md`, AUR packaging under
  `packaging/aur/`, and a tag-triggered `release.yml` that refuses to publish
  when the tag and the package version disagree.

[0.3.0]: https://github.com/<your-username>/deskmark/releases/tag/v0.3.0
