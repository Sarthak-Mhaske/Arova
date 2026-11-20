# Contributing

Small project, two rules.

**1. Every promise gets a test.** The interesting tests here are promises, not
coverage: "an empty reference is refused", "a corrupt index is a cache miss",
"a recorded command is never executed", "a 429 never echoes your API key". If
you change behaviour, change the test that pins it.

```bash
python -m pip install -e .
python -m pytest -q          # 61 tests, no network, under a second
```

**2. Nothing new may leave the machine.** The product's only real asset is that
`deskmark save` sends nothing anywhere. A feature that phones home, adds
telemetry, or requires an account will be rejected, however useful.

## Good first contributions

- A provider for an editor or terminal emulator that is not detected yet
  (`deskmark/providers/`, one function, one test).
- A platform note in `docs/SPEC.md` when capture differs on macOS or Windows.
- A failing conformance case in `docs/CONFORMANCE.md` — writing the rule is as
  valuable as implementing it.

## What gets merged quickly

- Fixes to error messages that turn a traceback into a hint.
- Anything that makes restore more faithful on Linux, with the measured
  before/after in the PR description.
- Documentation corrections. Especially where the docs promise more than the
  code does.

## What gets declined

- Dependencies. The project is standard library only, on purpose.
- Daemons, background watchers, and always-on capture.
- Anything that stores screenshots or screen content by default.
