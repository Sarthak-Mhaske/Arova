# Roadmap

The plan and its reasoning live in [`PIVOT.md`](PIVOT.md). This file is the checklist.

The rule for every item: **does it make resuming work faster, or make the format more
trustworthy for someone who did not write it?** If not, it waits.

---

## v0.1 — shippable (weeks 1–2)

- [x] `arova.resume/v1` format + spec (`docs/RESUME_POINT.md`)
- [x] `save` / `resume` / `list` / `show` / `packet` / `doctor` / `hooks` / `gc`
- [x] MCP server, dual-era (`server/discover` + `initialize`)
- [x] Privacy policy on host + path, with counted redactions
- [x] Apache-2.0 `LICENSE`
- [x] Zero runtime dependencies
- [x] 35 tests pinning round-trip, privacy, honest intent, never-execute
- [ ] `pipx install arova` published to PyPI
- [ ] 40-second demo GIF (the single most important asset)
- [ ] CI: Linux + macOS + Windows × Python 3.9–3.13
- [ ] Delete the kill list in `PIVOT.md` §5; keep `attic/` one release

## v0.2 — stickiness (weeks 3–8)

- [ ] Auto-checkpoint hooks for Claude Code, Codex, Cursor (`SessionStart` / `Stop`)
- [ ] VS Code / Cursor extension: real open editors, unsaved state
- [ ] `arova diff <a> <b>` — what changed between two points
- [ ] Cross-machine resume: a point committed to a repo resumes on another laptop
- [ ] Restore adapters: Zed, JetBrains, tmux layouts, macOS Spaces, Windows virtual desktops
- [ ] `arova packet --for <agent>` presets (Claude Code, Codex, Cursor, generic)

## v0.3 — decide the business (weeks 9–12)

- [ ] Instrumented retention: % of resumes followed by 10 minutes of work
- [ ] Five discovery calls with firms that cannot record screens (option B in §7)
- [ ] Team sync RFC: E2E-encrypted, self-hostable, points stay local by default

---

## Deliberately not doing

- Screenshots, OCR, audio, video. **Zero pixels is the wedge.** Losing it loses the product.
- A desktop app as the primary surface. The CLI and the format are the product.
- A daemon. If it cannot run on demand in under a second, it is the wrong design.
- A hosted agent. The labs are building those; we are the memory of the human between them.
- Replaying recorded commands on restore. Ever.

---

## Kill criteria (from `PIVOT.md` §8)

- 30 days post-launch: <100 stars **and** <3 non-author weekly users → the wedge is wrong.
- 90 days: <25% of saved points ever resumed → reconsider the verb.
- 6 months: no path to five paying teams or an adopted standard → fold the format into a
  larger tool instead of maintaining a museum.
