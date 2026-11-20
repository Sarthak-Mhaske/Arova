# Changelog

All notable changes to this project are documented here.
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
  explicit `verify()`, and forward-only versioning. See `docs/SPEC.md`.
- `deskmark mcp`: a stdio MCP server (`resume_latest`, `resume_list`,
  `resume_point_save`, `resume_open_next`, `resume_plan`) that speaks both the
  2025-06-18 and 2026-07-28 protocol eras.
- `deskmark look [question]`: one screenshot, one question, answered with your
  own API key (Gemini, OpenAI or Anthropic). No daemon, no recording, no history.
- `deskmark hooks`: an optional shell hook that records exit codes and the last
  failure in each directory, so "next step" has something real to say.
- `deskmark doctor`: reports what this machine can actually capture.

### Notes
- Zero runtime dependencies. Everything above is standard library only.
- Recorded shell commands are context, never instructions: restore reopens a
  workspace and never replays a command.

[0.3.0]: https://github.com/<your-username>/deskmark/releases/tag/v0.3.0
