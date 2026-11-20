#!/usr/bin/env bash
# Build a throwaway "developer machine" and run the resume point demo against it.
#
#   ./scripts/demo.sh            # save + show + dry-run restore
#   ./scripts/demo.sh --clean    # remove the fixture afterwards
#
# Everything happens under /tmp/arova-demo and never touches your real HOME,
# browser profile, or ~/.arova store.
set -euo pipefail

ROOT="${AROVA_DEMO_DIR:-/tmp/arova-demo}"
PY="${PYTHON:-python3}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "${1:-}" = "--clean" ]; then rm -rf "$ROOT"; echo "removed $ROOT"; exit 0; fi

rm -rf "$ROOT"; mkdir -p "$ROOT/home/.local/share/arova" "$ROOT/home/.config/google-chrome/Default" \
  "$ROOT/code/acme/api/src/webhooks" "$ROOT/bin"

export HOME="$ROOT/home"
export AROVA_HOME="$ROOT/home/.arova"
export XDG_DATA_HOME="$ROOT/home/.local/share"
export PYTHONPATH="$REPO_DIR"

cd "$ROOT/code/acme/api"
git init -q .; git config user.email demo@arova; git config user.name demo
printf 'def handle(event):\n    return {"ok": True}\n' > src/webhooks/handler.py
printf 'def verify(sig, body, secret):\n    return True\n' > src/webhooks/signature.py
git add -A; git commit -qm "webhooks: accept delivery and verify signature"
git checkout -q -b feat/checkout-idempotency
printf 'def handle(event):\n    # TODO: backfill duplicate-delivery test before enabling retries\n    return {"ok": True}\n\nRETRY_POLICY = {"attempts": 3, "idempotency_required": True}\n' > src/webhooks/handler.py
printf '# FIXME: decide whether idempotency keys live in the envelope or the DB\nSTORES = {}\n' > src/webhooks/idempotency.py

cat > "$XDG_DATA_HOME/arova/session_log.jsonl" <<'JSON'
{"timestamp":"2026-11-20T09:12:04+00:00","type":"terminal_command","data":{"command":"pytest tests -k retry","cwd":"__CWD__","cmd_id":"c1","cmd_type":"test_run"}}
{"timestamp":"2026-11-20T09:12:19+00:00","type":"terminal_output","data":{"command":"pytest tests -k retry","cmd_id":"c1","exit_code":1,"duration_ms":14920}}
JSON
sed -i "s|__CWD__|$ROOT/code/acme/api|g" "$XDG_DATA_HOME/arova/session_log.jsonl"

mkdir -p "$HOME/.claude/projects/$(echo "$ROOT/code/acme/api" | tr '/' '-')"
: > "$HOME/.claude/projects/$(echo "$ROOT/code/acme/api" | tr '/' '-')/8f2c1e4a-77b3-4c19-9f11-2b6d5a0c3e77.jsonl"

"$PY" - <<PY
import sqlite3, time
db = "$HOME/.config/google-chrome/Default/History"
c = sqlite3.connect(db).cursor()
c.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, last_visit_time INTEGER)")
now = int((time.time() + 11644473600) * 1_000_000)
for i, (u, t) in enumerate([
    ("https://github.com/acme/api/pull/412", "(3) Add checkout idempotency by dev · Pull Request #412"),
    ("https://stripe.com/docs/webhooks/best-practices", "Webhook best practices | Stripe Documentation"),
    ("https://chase.com/payments/transfer", "Transfer funds | Chase"),
    ("https://mail.google.com/mail/u/0", "Inbox (17)"),
]):
    c.execute("INSERT INTO urls (url,title,last_visit_time) VALUES (?,?,?)", (u, t, now - i * 600_000_000))
c.connection.commit()
PY

# a stand-in for a running agent, so the agent section is populated
printf '#!/bin/sh\nsleep 30\n' > "$ROOT/bin/claude"; chmod +x "$ROOT/bin/claude"
setsid "$ROOT/bin/claude" >/dev/null 2>&1 < /dev/null &
sleep 0.4

cd "$ROOT/code/acme/api"
echo "── arova save ─────────────────────────────────────────────"
"$PY" -m arova.resume save "checkout-idempotency"
echo
echo "── arova packet ───────────────────────────────────────────"
"$PY" -m arova.resume packet
echo
echo "── arova resume (dry run) ─────────────────────────────────"
"$PY" -m arova.resume resume
