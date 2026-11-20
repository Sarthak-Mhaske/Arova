# Security policy

Deskmark reads a developer's working state: repository paths, branch names,
shell history, browser tabs, agent sessions. Its security model is that none of
it leaves the machine, and the filter that decides what is recorded is the most
important code in the project.

## Reporting

Open a [private security advisory](https://github.com/<your-username>/deskmark/security/advisories/new)
or email the maintainer. Please do not open a public issue for anything that
leaks data. Expect an answer within a week. There is no bounty — this is a
free, Apache-2.0 project and there is no revenue to pay one from.

## In scope

- **A bypass of the redaction filter** — a page, URL shape, command or file path
  that lands in a resume point though policy says it must not.
- **A credential reaching disk** — an API key, token or password in a point,
  the index, or the session log.
- **Execution of recorded content** — any path where restore, MCP or `look`
  runs a command that came from a point, a packet or a client.
- **Path traversal or arbitrary read** — an MCP client or a crafted point making
  Deskmark read outside `DESKMARK_HOME` or outside the point it was asked for.
- **The MCP server treating a point as instructions** — a point whose content
  changes what the server does, rather than what it reports.
- **A leaked key in an error message** — provider errors must never echo the
  key, and `429` handling is tested for exactly that.

## Out of scope

- Anyone with read access to `$DESKMARK_HOME` reading your points. They are
  plain text on purpose; a resume point is not a secret store. Use full-disk
  encryption.
- Tabs recorded from a browser profile you did not expect — check
  `deskmark doctor`, and remove the profile.
- The privacy of anything you paste into an MCP prompt.
- `deskmark look` sending one screenshot to the provider you configured. That is
  the feature; it is documented, one-shot, and off unless invoked.

## What is never recorded

Screenshots, screen content, OCR text, keystrokes, window titles (except the
focused window name, only when `look --window` asks for it, and never stored),
file contents, and page titles. If you find any of those in a point, that is a
bug worth reporting.
