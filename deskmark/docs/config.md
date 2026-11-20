# Configuration reference

Deskmark has no config file. Everything is an environment variable, a flag, or a
file on disk. That is deliberate: a config file is a thing that can drift out of
sync with reality, and there is nothing here worth that risk.

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `DESKMARK_HOME` | `~/.deskmark` | Where points, the index and the session log live. Everything follows this one variable. |
| `DESKMARK_EDITOR` | auto-detect | Editor used for `resume` (e.g. `zed`, `code --wait`). Auto-detect tries `code`, `cursor`, `zed`, `subl`, `code-insiders`, `windsurf`. |
| `DESKMARK_LOOK_MODEL` | per provider | Model override for `look`, e.g. `gemini-3-flash`. |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | — | Vision key for `look`, provider `gemini`. |
| `OPENAI_API_KEY` | — | Vision key for `look`, provider `openai`. |
| `ANTHROPIC_API_KEY` | — | Vision key for `look`, provider `anthropic`. |

Nothing else is read. In particular Deskmark never reads a proxy, telemetry or
analytics variable, because it makes no calls of its own.

`XDG_DATA_HOME` is honoured for the session log **only when `DESKMARK_HOME` is
not set**, so the store and the log can never end up in different places.

## Files

```
$DESKMARK_HOME/                      (default ~/.deskmark)
├── points/
│   └── 2d3689204957.json            one file per resume point
├── index.json                       cache: list + summaries, rebuilt on damage
├── session_log.jsonl                written by the shell hook, read by capture
└── shell_hook.sh                    copied here by `deskmark hooks`
```

Everything is plain text. `cat`, `jq`, `grep`, `diff` and `git` all work on it.

## Flags

### `deskmark save [name]`

| Flag | Default | Meaning |
|------|---------|---------|
| `name` | intent-shaped, e.g. `checkout-idempotency` | Positional; the label you will search by |
| `-C`, `--cwd` | current directory | Which directory to capture |
| `-n`, `--note` | — | Why this work exists |
| `--why` | inferred | Override the inferred `why` |
| `--next` | inferred | The single next action |
| `--window` | `12` | Hours of shell log to consider |
| `--no-browser` | off | Skip browser session files entirely |
| `--no-agents` | off | Skip the agent scan |
| `--json` | off | Print the point as JSON |

### `deskmark resume [ref]`

| Flag | Meaning |
|------|---------|
| `--yes` | Actually open things. Without it, print the plan and stop. |
| `--no-files` | Do not open files |
| `--no-tabs` | Do not open tabs |
| `--no-shells` | Do not open terminals |
| `--core-only` | Skip optional actions |
| `--json` | Print the plan as JSON |

### `deskmark list`

`--limit N` (default: all), `--fresh` (hide stale points), `--json`.

### `deskmark show [ref]` / `deskmark packet [ref]`

`--budget N` — characters, default `4000` for both `show` and `packet`.
Sections are dropped lowest-priority first; the footer names what was omitted.

### `deskmark gc`

`--max 200` (keep the newest N), `--days 30` (delete older than N days). Both
apply; a point must survive both to be kept.

### `deskmark hooks`

`--dry-run` prints the exact line that would be appended. `--uninstall` removes
the block between the markers. The hook is idempotent: running install twice
changes nothing.

### `deskmark look [question]`

`--image PATH` (use a file instead of a screenshot), `--window` (include the
focused window name), `--provider {gemini,openai,anthropic}`, `--model NAME`,
`--json`. Default question: "explain this screen".

### `deskmark doctor [--look-keys]`

No other flags. `--look-keys` adds whether a vision key is present, never its
value.

## References

A `ref` may be:

- a full point id — `2d3689204957`
- a unique id prefix of at least 2 characters — `2d`
- a point name — `checkout-idempotency`

Ambiguous prefixes and empty refs are errors. Deskmark never picks a point for
you, because picking wrong means restoring the wrong desk.

A new point gets a random 12-hex id. That id is a label, not a checksum — the
`digest` field is the sha256 prefix over canonical JSON, and `verify()` is what
proves a point has not been altered. Points are `2–4 KB` on a normal desk.

## Shell hook

`deskmark hooks` appends this to `~/.bashrc` and `~/.zshrc` (whichever exists),
between markers so it can be removed cleanly:

```bash
# >>> deskmark shell hook >>>
[ -f "$HOME/.deskmark/shell_hook.sh" ] && source "$HOME/.deskmark/shell_hook.sh"
# <<< deskmark shell hook <<<
```

(The path is `$DESKMARK_HOME/shell_hook.sh`; the block writes it out in full.)

The hook records command text, cwd, exit code and duration, and the last 50
lines of output **only for commands that failed**. It does not wrap your shell
in a PTY, does not change command behaviour, and writes only to
`session_log.jsonl`.
