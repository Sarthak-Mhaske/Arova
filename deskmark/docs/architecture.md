# Architecture

Deskmark is a single Python process that starts, does one thing, and exits. There
is no daemon, no server, no port, and no background worker. That constraint
decides almost every other design choice in this document.

```
                     deskmark save
                          │
              ┌───────────┴────────────┐
              │      capture.py        │  builds one ResumePoint
              └───────────┬────────────┘
     ┌────────────┬───────┴──────┬─────────────┬──────────────┐
 providers/repo  providers/   providers/    providers/    intent.py
   (git)         terminal     sessions     agents        (why / next)
              └───────────┬────────────┘
                          │  schema.py  validate + digest
                          ▼
                    store.py  ~/.deskmark/points/<id>.json
                          │
        ┌─────────────────┼──────────────────┐
        ▼                 ▼                  ▼
   packet.py          restore.py           mcp.py
 (context for       (plan → apply)      (stdio server)
  humans/agents)
                          ▲
                     cli.py  (argparse, text output)
```

## Modules

| Module | Responsibility | Invariant |
|--------|----------------|-----------|
| `schema.py` | The `deskmark/v1` dataclasses, validation, digest | A point is valid before it is written, and its digest verifies after |
| `capture.py` | Assembling one point from providers | A provider that fails becomes a warning, never an exception |
| `intent.py` | Inferring *why* and *next* | Inference is always labelled as inference, and `--why` / `--next` always win |
| `store.py` | Where points live | The index is a cache; the point files are the truth |
| `packet.py` | Rendering a point as bounded text | Output never exceeds the budget, and never includes file contents |
| `restore.py` | Turning a point into actions | `plan()` touches nothing; `apply()` is opt-in |
| `mcp.py` | stdio MCP server | Every response carries the request id |
| `cli.py` | The human surface | Errors are one line plus a hint, never a traceback |
| `hooks.py` | Installing the shell hook | Idempotent, appended between markers, uninstallable |
| `providers/` | Reading the machine | Each provider reports confidence and TTL, or says why it could not |

## Data flow, concretely

1. `capture()` resolves `cwd`, then asks each provider for one part of the
   picture: repo (`providers/repo.py`), shells (`providers/terminal.py`), tabs
   (`providers/sessions.py`), agents (`providers/agents.py`).
2. Each provider goes through `providers.Collector`, which records the value,
   the source, a confidence, and a TTL — or a skip reason with a human-readable
   message. The collector is what `deskmark doctor` and the "not captured" footer
   of a packet read from.
3. The working set is ordered: repo root first, then open or changed files, then
   shell roots. Files that no longer exist are dropped. Secrets are redacted
   before anything is serialised.
4. `schema.ResumePoint` computes a digest over canonical JSON (sorted keys, no
   whitespace). The id is the first 16 hex characters.
5. `store.save()` writes the point file atomically: temp file, `fsync`,
   `os.replace`. Then it updates `index.json`, which is a cache. If the index is
   corrupt or stale, the next read rebuilds it from the files.
6. `packet.render()` produces ordered sections — where you were, why/next, files,
   agents, terminals, tabs, open questions — and drops the lowest-priority
   sections first when it hits the character budget.
7. `restore.plan()` is pure. `restore.apply(dry_run=False)` spawns editors,
   file managers, browsers and terminals through the platform opener. It never
   runs a recorded command and never synthesises keystrokes.

## Invariants worth knowing before you change anything

**Zero pixels.** No module may capture screen content, window titles, OCR text,
or keystrokes. `look/` is the single exception: it is invoked by the user, one
shot, and writes nothing to disk.

**Privacy decisions are made on host and path.** `providers/privacy.py` never
matches free text. Filtering on titles deletes real work silently, and silent
data loss is worse than a leak you can see.

**Never execute recorded commands.** Restore reopens a workspace. Commands in a
point are text to be read. Any change that turns them into something executed is
a security bug, not a feature.

**Every ambient input is optional.** A machine with no git, no browser, no shell
hook and no `/proc` still produces a valid point with fewer parts and honest
`not captured` notes.

**Degrade, do not raise.** Providers catch their own failures. The only errors
that reach the CLI are `DeskmarkError` subclasses with a written hint
(`deskmark/errors.py`) — a traceback in front of a user is a bug report.

**The store is the only writer.** No module writes to `~/.deskmark/` except
`store.py`; the shell hook writes only `session_log.jsonl`.

## Why there is no daemon

A daemon would let Deskmark notice context switches and pre-compute points. It
would also mean a permanent process, a port or a socket, a stream of state
leaving the CLI invocation, and a privacy story that depends on configuration.
The trade was made the other way: capture is fast enough (tens of
milliseconds) that an explicit `deskmark save` is not a burden, and nothing is
ever recorded when you did not ask.
