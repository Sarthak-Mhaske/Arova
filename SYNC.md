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

## Publish it (once, by hand)

```bash
cd deskmark
git init -b main
git add . && git commit -m "deskmark 0.3.0"
gh repo create deskmark --private --source . --push   # or --public, your call
```

Then replace the `<your-username>` placeholder in `pyproject.toml` (2 URLs),
`README.md` (1 badge + 1 releases link) and `CHANGELOG.md` (1 link):

```bash
grep -rn "<your-username>" .        # 4 hits, all cosmetic
```

## Verified before handover

- `python -m pytest -q` → **67 passed in 0.61s**
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
