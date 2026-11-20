# Conformance

Anything that claims to read or write `deskmark/v1` must pass these. They are
written so a second implementation in another language (the Rust port is on the
roadmap) can be checked against the same file, without reading the Python.

## The point itself

1. **Round trip.** Serialise a point, parse it back, serialise again: the two
   outputs are byte-identical.
2. **Digest.** `digest` is the first 16 hex characters of the sha256 of the
   canonical JSON of the point *excluding* the `digest` field, with keys sorted
   and no whitespace. `verify()` recomputes it and refuses a mismatch.
3. **Versioning is forward-only.** `schema` must be `deskmark/v1`; a point
   whose `version` is greater than the reader's must be refused, never
   silently degraded.
4. **Size.** A point is bounded to roughly 64 KB. Capture that would exceed it
   drops items (oldest first) rather than truncating a field mid-string.
5. **Unknown fields are preserved, not dropped**, when a point is loaded and
   re-saved by an older reader.

## References

6. An empty reference is an error, not a wildcard.
7. A reference that matches more than one point by prefix is an error; the
   store never guesses.
8. A filesystem path is only accepted where the caller explicitly opted into
   paths. It is never accepted from a network or MCP caller.

## The store

9. The index is a cache. If it is corrupt, missing, or stale, the store
   rebuilds it from the point files and continues.
10. A damaged point file is skipped when listing, not surfaced with an error
    that stops the listing.
11. An index entry whose file has been deleted is dropped, and the next lookup
    says so instead of failing obscurely.

## Restore

12. `plan` is pure: it reads a point and returns a plan, touching nothing.
13. `apply` is opt-in. Without it, nothing is opened, spawned or written.
14. Recorded commands are displayed in the plan, never executed.
15. Restoring opens editors, URLs and terminal emulators only. It does not
    replay a shell, and it does not synthesise keystrokes.

## MCP

16. Every response carries the request's `id`. A response without it is not
    JSON-RPC and is a conformance failure.
17. `initialize` negotiates the requested protocol version when it is
    supported, and otherwise answers with the newest version it knows.
18. `server/discover` and `tools/list` are answerable without touching the
    store, so a fresh machine can connect before it has ever saved a point.
