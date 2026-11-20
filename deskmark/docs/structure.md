# Repository layout

```
deskmark/
├── deskmark/                    the package
│   ├── __init__.py              SCHEMA_ID, SCHEMA_VERSION, __version__
│   ├── __main__.py              `python -m deskmark`
│   ├── schema.py                deskmark/v1 dataclasses, validation, digest
│   ├── store.py                 point files, index-as-cache, gc
│   ├── capture.py               build one point from the providers
│   ├── intent.py                infer why / next, and say where it came from
│   ├── packet.py                bounded text + json rendering for agents
│   ├── restore.py               plan (pure) → apply (opt-in)
│   ├── mcp.py                   stdio MCP server
│   ├── hooks.py                 install / remove the shell hook
│   ├── cli.py                   argparse surface, all output
│   ├── errors.py                DeskmarkError + hint discipline
│   ├── providers/
│   │   ├── __init__.py          Collector: value + source + confidence + TTL
│   │   ├── repo.py              git ground truth, working set, open questions
│   │   ├── terminal.py          shell hook log + /proc merge
│   │   ├── agents.py            coding agents and resumable session ids
│   │   ├── sessions.py          open tabs, from the browser session log
│   │   └── privacy.py           the allow/drop rules. host + path only
│   ├── look/
│   │   ├── screen.py            screenshot + focused window, per platform
│   │   ├── understand.py        one vision request, your key, stdlib urllib
│   │   └── errors.py            LookError
│   └── hooks/
│       └── shell_hook.sh        vendored, shipped inside the wheel
├── tests/
│   ├── conftest.py              shared home / png fixtures
│   ├── test_core.py             format, store, capture, restore, MCP
│   └── test_look.py             capture ordering, payloads, key hygiene
├── docs/
│   ├── spec.md                  the deskmark/v1 specification
│   ├── conformance.md           rules any other implementation must pass
│   ├── architecture.md          modules, data flow, invariants
│   ├── providers.md             what is detected, per tool
│   ├── config.md                flags, environment, files
│   ├── structure.md             this file
│   ├── testing.md               how to run and extend the tests
│   └── demo.tape                VHS script that renders the demo GIF
├── packaging/
│   ├── aur/PKGBUILD             Arch package
│   ├── aur/.SRCINFO             generated metadata, committed on purpose
│   └── RELEASE.md               release checklist
├── scripts/demo.sh              throwaway demo machine in /tmp
├── .github/workflows/           ci.yml (3 OS × 3 Python), release.yml (tag)
├── AGENTS.md                    instructions for a coding agent
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
├── pyproject.toml               hatchling, zero runtime dependencies
└── LICENSE                      Apache-2.0
```

## Conventions

- **One module, one job.** If a module needs a diagram to explain, it is two
  modules. `privacy.py` exists as its own file because it is the most important
  rule in the product and deserves to be readable in one screen.
- **Providers share one shape:** a function that returns data or raises nothing,
  plus a `Collector` call that records source, confidence and TTL.
- **The CLI prints, modules return.** Only `cli.py` and `restore.apply` write to
  stdout. Everything else returns values, which is why the tests can assert on
  them.
- **Errors carry hints.** `DeskmarkError(message, hint=...)`. `cli.py` prints
  `error:` then `hint:`. No stack traces reach a user.
- **No dependency is free.** `dependencies = []` is a feature with a test
  forbidding it from being quietly relaxed: every import outside the standard
  library is a decision, not a convenience.
