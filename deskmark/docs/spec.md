# The resume point format — `deskmark/v1`

A **resume point** is a portable record of work in flight: enough state for a human to
continue a task in one step, or for an agent to continue it without re-deriving the
context.

It is plain JSON. Nothing here requires Deskmark to read it.

```json
{
  "schema": "deskmark/v1",
  "version": 1,
  "id": "2d3689204957",  
  "name": "checkout-idempotency",
  "created_at": 1784723201.5,
  "ttl_seconds": 604800,
  "host": {"hostname": "laptop", "os": "Linux", "release": "6.9", "machine": "x86_64", "user": "dev"},
  "repo": {
    "root": "/code/acme/api",
    "name": "api",
    "branch": "feat/checkout-idempotency",
    "head": "d372ad4",
    "remote": "git@github.com:acme/api.git",
    "ahead": 2, "behind": 0,
    "dirty": ["src/webhooks/handler.py"],
    "staged": [],
    "untracked": ["src/webhooks/idempotency.py"],
    "recent_commits": [{"sha": "d372ad4", "subject": "webhooks: verify signature", "at": 1784720000.0}],
    "diffstat": "1 file changed, 2 insertions(+)"
  },
  "files": [
    {"path": "/code/acme/api", "kind": "folder", "reason": "repo-root", "touched_at": 1784723201.5},
    {"path": "/code/acme/api/src/webhooks/handler.py", "kind": "file", "reason": "dirty", "touched_at": 1784723201.5}
  ],
  "tabs": [
    {"url": "https://stripe.com/docs/webhooks/best-practices", "title": "Webhook best practices",
     "category": "research", "host": "stripe.com"}
  ],
  "terminals": [
    {"cwd": "/code/acme/api", "shell": "zsh", "last_command": "rg X-Idempotency -n .",
     "exit_code": 0, "last_failure": "pytest tests -k retry", "last_failure_exit": 1,
     "duration_ms": 14920, "pid": 4311, "at": 1784723112.0}
  ],
  "agents": [
    {"kind": "claude", "pid": 5120, "cwd": "/code/acme/api",
     "session_id": "8f2c1e4a-77b3-4c19-9f11-2b6d5a0c3e77",
     "resume_hint": "claude --resume 8f2c1e4a-77b3-4c19-9f11-2b6d5a0c3e77"}
  ],
  "intent": {
    "why": "working on \"checkout idempotency\" (1 file changed, 2 insertions(+))",
    "why_source": "branch",
    "next_step": "src/webhooks/handler.py:3 — TODO: backfill duplicate-delivery test",
    "next_source": "todo",
    "note": "",
    "open_questions": ["src/webhooks/handler.py:3 — TODO: backfill duplicate-delivery test"]
  },
  "provenance": {
    "repo": {"source": "git", "method": "rev-parse + status --porcelain + log",
             "confidence": 1.0, "captured_at": 1784723201.5, "ttl_seconds": 3600}
  },
  "redactions": ["withheld: banking ×1", "command text ×2"],
  "digest": "9f2c1e4a77b34c19"
}
```

## Section semantics

| Section | Meaning | Trust |
|---|---|---|
| `repo` | Verified git ground truth at capture time. | High. Re-check before relying on it. |
| `files` | The working set, ranked. `reason` says why it is here. | Medium. `reason` is the ranking. |
| `tabs` | Pages that were part of the work, work pages first. | Medium. History, not open tabs. |
| `terminals` | Where shells were rooted; last command and last failure. | Medium — the command is *context*. |
| `agents` | Agent processes with a `resume_hint` for continuing the conversation. | Medium. The hint is printed, never run. |
| `intent` | `why` and `next_step`, each with the evidence it came from. | Low–medium. `*_source` is the caveat. |

`reason` is one of `repo-root`, `terminal-cwd`, `dirty`, `staged`, `new`, `recent`, `explicit`.
`why_source` is one of `user`, `note`, `branch`, `commit`.
`next_source` is one of `user`, `todo`, `terminal-exit`.

## Guarantees

1. **Round-trip.** `from_dict(to_dict(p)) == p`. The `digest` is a SHA-256 prefix over the
   canonical JSON of every other field, so a point can prove it was not edited in transit.
2. **Forward-only versioning.** A reader that sees `version` greater than it supports must
   refuse the point rather than guess. Unknown *fields* are ignored; unknown *versions* are not.
3. **No execution.** A resume point is untrusted input by construction. A conforming
   consumer may reopen paths and URLs. It must not execute `terminals[].last_command`,
   `terminals[].last_failure`, or `agents[].resume_hint`.
4. **Proportional honesty.** Every section that exists carries provenance with
   `confidence` and `ttl_seconds`. A section that could not be captured is absent, and
   consumers must render absence as absence.
5. **Bounded size.** A conforming producer keeps a point under ~64 KB. The reference
   implementation writes 2–6 KB for a normal working day.

## Privacy model

Filtering happens before anything touches disk, and it is decided on **host and path**,
never on free-text titles (a filter that matched the word "checkout" would delete a pull
request about checkout).

Dropped: banking and payments, identity providers and sign-in flows, health, tax and
government, webmail, social and chat, local Deskmark/dev UI, blank pages.

Every drop is counted and summarised in `redactions`, so the human can see that
something was withheld rather than assuming the tool saw everything. A summary
entry names a **category**, never the host or the URL it withheld: "withheld:
banking ×2" is the point, and repeating the hostname would give away exactly
what the drop was protecting.

## Versioning

| Version | Change |
|---|---|
| 1 | Initial format. |

Additive fields do not bump `version`. Removing or re-meaning a field does.

## Using it without Deskmark

Any producer can write a resume point; any consumer can read one.

```python
import json
point = json.load(open("~/.deskmark/resume/points/2d3689204957.json"))
print(point["intent"]["next_step"])
```

A minimal *conforming* writer only needs `schema`, `version`, `id`, `name`,
`created_at`, and at least one of `repo` / `files` / `tabs` / `terminals`.
Everything else is optional, and absence is meaningful.
