# Contributing to Arova

Arova is **resume points for your whole desk**: a small, open format for work in
flight, plus the one command that puts your desk back. Read [`PIVOT.md`](PIVOT.md)
for why, and [`docs/RESUME_POINT.md`](docs/RESUME_POINT.md) for the format.

---

## The bar

One question decides every pull request:

> **Does this make resuming work faster, or make the format more trustworthy for
> someone who did not write it?**

If the honest answer is "it makes the demo look better", it waits.

## The four rules

These are architecture, not taste. A change that breaks one of them will be rejected
regardless of how well it works.

1. **Zero pixels.** No screenshots, OCR, audio, or video capture — not as an option,
   not behind a flag. If Arova ever records a pixel, the reason to trust it is gone.
2. **Resume, not search.** Features exist to get someone back to work. Search over the
   past is a different product with well-funded incumbents.
3. **Never execute recorded commands.** A resume point is untrusted input: it may have
   travelled between machines or been written by an agent. Restore reopens paths and
   URLs. It prints commands; it does not run them.
4. **Say what is missing.** Absence is rendered as absence, with `provenance`,
   `confidence` and `ttl_seconds`. No fallback values that pretend to be live state.

## Code conventions

- **Zero runtime dependencies** in `arova/resume/`. Standard library only. A capture
  provider that cannot run should degrade to "not captured", never raise.
- **Every capture provider is fallible by design.** Wrap it, record a warning, move on.
  A broken capture path must never break `save`.
- **Tests pin promises, not lines.** Add a test that fails when the promise breaks.
  `pytest` must stay green; it runs 35 tests in under a second.
- Keep a resume point small. 2–6 KB is normal; over 64 KB is a bug.
- Python 3.9+ compatible. No walrus-in-comprehension cleverness.

## Adding a capture provider

1. Put it in `arova/resume/providers/`.
2. Return plain data from `schema.py`, or `None` for "not available here".
3. Add it to `capture.py` inside a `try`, with a `collector.skip(...)` reason.
4. Record provenance: source, method, confidence, ttl.
5. Add a test with a fixture — not with your real machine.
6. If it can see anything personal, route it through `privacy.classify()` first and
   count what you drop.

## Adding a platform adapter

`arova/core/platform/` is the surviving part of the previous product and is the best
code in the repository. Extend `Capability` rather than adding OS-specific branches to
the planner, and always return a `LaunchResult` with a verified outcome.

## Local development

```console
$ python -m pip install -e ".[dev]"
$ pytest                       # 35 tests, no network, no daemon
$ python -m arova.resume doctor
$ AROVA_HOME=/tmp/arova-dev python -m arova.resume save demo
```

Nothing in the test suite reads your real browser, home directory, or store: the
`home` fixture redirects `HOME`, `AROVA_HOME` and `XDG_DATA_HOME` into a tmp path.

## What is frozen

`attic/` is the previous product (a desktop "cognitive operating system"). It is kept as
reference, is excluded from the test run, and is not accepting changes. The parts worth
keeping are being ported into `arova/platform/` and `arova/resume/providers/`.

## License

Apache-2.0. By contributing you agree your contribution is licensed under the same
terms. Note: the previous README claimed BSL/PolyForm; that claim was never true (there
was no `LICENSE` file) and is superseded. The format must be implementable by anyone,
including competitors — that is the point of a format.
