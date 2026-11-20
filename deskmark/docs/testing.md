# Testing

```bash
python -m pip install -e . && python -m pip install pytest
python -m pytest -q          # 113 tests, no network, ~0.5s
```

There are no fixtures that reach the internet, no fixtures that read your real
home directory, and no tests that need a browser, a compositor or a display.

The browser fixtures are written by hand, from the format: a `Session_*` file is
built record by record in `chrome_session()` and a firefox one is wrapped by
`firefox_session()`. That makes them good at pinning behaviour (a close marker
excludes a tab, a torn record stops the read) and weak at proving the layout is
right, because the same misreading would be on both sides. Two things cover that
gap: the command ids and pickle layout come from `components/sessions` in
chromium, and `lz4_block()` was checked against the reference `lz4` module on
eighteen compressed payloads, both compression modes, including incompressible
data.
Every test that touches the filesystem uses `tmp_path`, and every test that
needs a home directory uses the `home` fixture, which redirects `HOME`,
`DESKMARK_HOME` and `XDG_DATA_HOME` into a temp directory.

`tests/conftest.py` holds the two shared fixtures:

| Fixture | Gives |
|----------|-------|
| `home` | an isolated `$HOME` with `DESKMARK_HOME` and `XDG_DATA_HOME` inside it |
| `png_file` | a 1×1 PNG on disk, for the `look` payload tests |

Do not define a second `home` fixture inside a test module: the module-level one
silently shadows the shared one and the tests that assumed the other home fail in
a way that looks like a product bug.

## What the tests are actually pinning

These are promises, not coverage. If you break one, the product changed meaning.

**The format**
- a point round-trips through `to_dict` / `from_dict` unchanged
- the digest recomputes, and tampering with a field is detected
- a future `version` is refused, not silently degraded

**The store**
- a corrupt `index.json` is a cache miss, not a crash
- a truncated point file is skipped when listing, not fatal
- an empty ref is an error; an ambiguous prefix is an error; `MIN_PREFIX` is 2
- writes are atomic: a partial file can never replace a good one

**Privacy**
- a sensitive host is dropped on host and path, and the title is never consulted
- a secret in a command never appears in the serialised point
- the redaction summary counts drops without repeating URLs

**Restore**
- `plan()` is pure: it opens nothing
- a recorded command appears in the plan and is never executed
- a missing editor degrades to the file manager with a note, not an exception

**MCP**
- every response carries the request id
- `initialize` negotiates the version it is given, and falls back forward
- `server/discover` and `tools/list` answer before any point exists

**`look`**
- capture tool order is deterministic per platform
- a 429 error message never echoes the API key
- an oversized image is refused with the size in the message
- payload shapes match for gemini, openai and anthropic

## Adding a provider

1. Write the function so it returns `None` / `[]` plus a reason, and never raises.
2. Register it in `capture.py` through `Collector.add(...)` with a source,
   confidence and TTL — or `Collector.skip(...)` with a human-readable reason.
3. Add it to `deskmark doctor` if a user can act on it.
4. Add two tests: one with the input present, one with it absent. The absent case
   is the one that keeps the promise "it never breaks because a machine is weird".

## The end-to-end check

`scripts/demo.sh` builds a throwaway desk in `/tmp` — a git repo, a fake session
log, a point — and exercises `save`, `list`, `show`, `packet`, `resume --json`
against it. It runs in the CI matrix as the CLI smoke test, so a broken entry
point cannot be released.

Manual, on a real machine, because CI cannot fake a compositor:

```bash
deskmark doctor
deskmark save smoke && deskmark resume          # plan only
deskmark resume --yes                           # now open it
deskmark hooks --dry-run && deskmark hooks      # then open a new shell
```

Restore fidelity is measured here, not in CI. The 1.1 milestone (see the
README roadmap) exists because this step is done by hand at the moment.

Not covered by anything above, and therefore not claimed anywhere: a real
chrome or firefox session file copied off a live profile, the restore outcome
itself, macOS and Windows, and python 3.9/3.10.
