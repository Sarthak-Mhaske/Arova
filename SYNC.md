# deskmark/ — the clean copy to hand to your own repo

`deskmark/` is a **complete, standalone project**. It is not a subpackage of
Arova and it imports nothing from Arova. The Arova tree stays exactly as it is
(my sandbox, with all the old context). Nothing in `deskmark/` refers to Arova,
`attic/`, `frontend/`, or any of the old code.

Copy the **contents** of `deskmark/` into your private repo, and that repo is
a finished, installable, testable project.

## What is in it

```
deskmark/
├── deskmark/                 # the package (~3,700 lines of Python, standard library only)
│   ├── schema.py  store.py   # the deskmark/v1 format, and where points live
│   ├── capture.py intent.py  # what is happening, and why
│   ├── packet.py  restore.py # agent packet, restore plan, apply
│   ├── mcp.py     cli.py     # the two surfaces
│   ├── errors.py  hooks.py
│   ├── providers/            # repo, terminals, agents, browser history, privacy
│   ├── look/                 # one screenshot, on request, with your own key
│   └── hooks/shell_hook.sh   # optional shell hook, shipped inside the wheel
├── tests/                    # 67 tests, no network, ~0.6s
├── docs/
│   ├── spec.md               # the deskmark/v1 format specification
│   ├── conformance.md        # what any other implementation must pass
│   ├── architecture.md       # modules, data flow, invariants
│   ├── providers.md          # what is detected, per editor/terminal/browser/agent
│   ├── config.md             # every flag, env var and file
│   ├── structure.md          # repository layout
│   ├── testing.md            # how to run and extend the tests
│   └── demo.tape             # VHS script for the demo GIF
├── packaging/
│   ├── aur/PKGBUILD + .SRCINFO   # Arch package
│   └── RELEASE.md            # release checklist
├── scripts/demo.sh           # throwaway demo machine in /tmp
├── .github/
│   ├── workflows/ci.yml      # 3 OS × 3 Python + wheel + MCP protocol smoke test
│   ├── workflows/release.yml # tag-triggered: version check, PyPI, GitHub release
│   └── ISSUE_TEMPLATE/       # bug report + feature request forms
├── pyproject.toml            # hatchling, zero dependencies, `deskmark` entry point
├── README.md  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  AGENTS.md
├── LICENSE (Apache-2.0)  .editorconfig  .gitignore
```

## Getting the folder out of Arova

The project lives on the branch **`arena/35f69639-arova`**, not on `main` —
`main` is still the old tree and has no `deskmark/` directory. A plain clone
lands on `main`, which is why `cp -r deskmark` fails with "No such file or
directory".

Two routes, both history-free:

```bash
# 1. sparse clone of the right branch (only that folder is written to disk)
git clone -b arena/35f69639-arova --single-branch \
    https://github.com/Sarthak-Mhaske/Arova.git arova-tmp
cp -r arova-tmp/deskmark ~/GIT/deskmark
rm -rf arova-tmp

# 2. from an existing clone, export just the folder
git archive --format=zip --prefix=deskmark/ HEAD:deskmark -o ~/deskmark.zip
```

`git init` afterwards starts a fresh history: the copied folder carries no
`.git`, because Arova's repo metadata stays behind in the clone.

## Publish it (once, by hand)

```bash
cd deskmark
git init -b main
git add . && git commit -m "deskmark 1.0.0"
gh repo create deskmark --private --source . --push   # or --public, your call
```

Then replace the `<your-username>` placeholder — 13 hits in 8 files, all
cosmetic (badge links in the README point at `../../releases`, which needs no
username at all):

```bash
grep -rn "<your-username>" .        # pyproject (3), README (2), AUR (3), rest (5)
```

## Presentation

The README follows the house style of `Sarthak-Mhaske/HyprVoice`: centred hero
with badge row and anchor nav, "Also known as", Overview, Demo with real console
transcripts, an ASCII pipeline, a status callout, features tables, Requirements +
Dependencies, Quick Install with a collapsible Manual Setup, Available Commands
by category, Configuration tables, Architecture, Platform support, collapsible
Troubleshooting, a Roadmap with checkboxes and a kill criterion, Provider
Support, File Structure, Documentation index, Contributing with commit format,
Acknowledgments, License.

There are no GIFs yet: the demo section uses the real output of
`./scripts/demo.sh`, and `docs/demo.tape` is the VHS script that renders them once
someone records.

## Verified before handover

- `python -m pytest -q` → **91 passed in 0.54s**
- a 47-probe hostile battery against the installed wheel: corrupt/truncated/
  non-UTF-8/tampered points, index as a directory, read-only store, a home that
  is a file, ref traversal, 300 changed files, newline and unicode filenames,
  detached HEAD, worktrees, secret-bearing commands, sensitive hosts, a restore
  canary that must not execute, headless restore, broken pipe, full disk, MCP
  traversal/batch/garbage input, 500 sequential MCP calls, 8 concurrent saves,
  gc racing list, clock skew, 200-point scale. All pass.
- `python -m build` → wheel + sdist; wheel is 28 files, ships the shell hook, contains no Arova reference
- wheel installed into a clean venv, then: `--version`, `doctor`, `save`, `list`, `packet`, `resume` (dry run), `mcp` (initialize + tools/list), `look` (error path)
- store layout is `~/.deskmark/{points,index.json,session_log.jsonl}` — no legacy `resume/` level

## How to keep it in sync

One direction only: **Arova → desktop copy**. `deskmark/` is where the project
lives now; `arova/resume` and `arova/look` are frozen history.

When I change something for you, I change it under `deskmark/`, and you copy
the files that changed. The cheap way to see what changed since your last copy:

```bash
cd /home/user/Arova
git log --oneline -- deskmark/                 # commits that touched the clean copy
git diff <last-synced-commit> HEAD -- deskmark/   # exactly what to apply
```

If you would rather sync by wholesale replace, delete the four project
directories in your repo (`deskmark/`, `tests/`, `docs/`, `.github/`) and copy
them across again. Nothing else ever needs to move.

## What did *not* come across

| Left behind | Why |
|---|---|
| `arova/core/` (31,789 lines) | the v0.1 desktop app; none of it is imported by the product |
| `attic/`, `frontend/` | frozen v0.1 UI |
| `arova/daemon/` | the product has no daemon, on purpose |
| `PIVOT.md`, `ROADMAP.md` | internal reasoning; `CHANGELOG.md` + README roadmap replace them |
| the old `shell_hook.sh` path & junk line | vendored properly inside the package, stray test line removed |
| `AROVA_*` env vars | now `DESKMARK_HOME`, `DESKMARK_EDITOR`, `DESKMARK_LOOK_MODEL` |
| `arova.resume/v1` | now `deskmark/v1` |
