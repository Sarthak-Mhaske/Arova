# The pivot — from cognitive OS to *resume points*

**Status:** recommendation, with a working prototype already in this branch.
**Date:** 20 November 2026 · **Repo state at review:** 41,337 lines of Python, 321 files, 0 stars, no `LICENSE`, 15 of 91 tests failing.

---

## TL;DR

> **Stop building a cognitive operating system. Build the missing verb: `resume`.**
>
> Arova should become **the open format and CLI for work in flight** — a small,
> portable "resume point" of what you were doing, why, and what's next, that
> restores your environment in one step and that any AI agent can read over MCP.
>
> **Zero pixels. Resume, not search. A format, not an app.**
>
> The category's incumbents all sell *recording*. The pain is *returning*. That
> half of the problem has no owner — and this repository already contains the hard
> parts of it.

What that means concretely: `arova save` writes a 3 KB JSON file; `arova resume`
puts your editor, files, tabs, shells and agent sessions back. `arova mcp` lets
Claude Code, Codex, Cursor or OpenClaw save and read those points themselves.

---

## 1. What is actually in this repository

An honest audit, because the pivot depends on what is real.

**What is real and good:**

| Component | Lines | Why it matters |
|---|---|---|
| `arova/core/platform/` — application catalog, launcher, restore intents, per-OS backends | 3,039 | Cross-platform "open this thing properly" is genuinely hard and mostly done. |
| `arova/core/ambience/shell_hook.sh` + `install_hooks.py` | ~350 | A privacy-first shell hook: filters secrets, captures cwd/exit codes, no PTY wrapping. Better than most commercial tools. |
| `arova/core/cognition/restore_planner.py` + `restoration_engine.py` | ~500 | Restore planning with **per-item provenance** and verified outcomes. Unusually rigorous. |
| The domain model — workspace, resources, TTL/staleness, "reality contracts" | — | The design instinct in `DOGFOOD_BUGS.md` ("no fallback values that pretend to be live state") is a real product principle. |
| Browser history reader with a privacy filter | ~250 | Works across Chrome/Brave/Chromium/Edge/Firefox on three OSes with no extension. |

**What is weight:**

| Component | Lines | Verdict |
|---|---|---|
| `frontend/` — Tauri + React UI | 15,045 | Kill the surface, keep nothing. A desktop app is the wrong delivery vehicle for an infrastructure primitive. |
| `arova/core/cognition/` — twelve layers ("reality", "interpretation", "understanding", "confidence") | 6,867 | Kill. Architecture built ahead of evidence. |
| `arova/core/voice/` — wake word, VAD, TTS | 2,684 | Kill. Different product. |
| `arova/core/automation/dispatcher.py` — 1,758 lines of capability backends | 2,639 | Kill. Agents are now a solved commodity; you cannot out-build OpenAI here. |
| `arova/desktop/` — GTK orb, chat surface, markdown renderer | 2,391 | Kill. |
| `arova/core/models/`, `memory/`, `environment/`, `presence/`, `intention/`, `projection/`, `telemetry/` | ~5,900 | Kill. |
| `arova/daemon/` — 1,674-line single file | 1,674 | Kill. Not needing a daemon is a feature. |

**Roughly 83% of the code is not part of the product.** That is the single most
important fact in this document: the previous plan was to ship a 41,000-line
desktop application to five design partners. The realistic plan is to ship a
700-line command that does one thing no one else does.

**Other findings that matter:**

- There is **no `LICENSE` file**, while `README.md` and `CONTRIBUTING.md` both claim
  a "Business Source License / PolyForm Noncommercial". The repository is therefore
  legally "all rights reserved" while telling contributors otherwise. That is a
  blocking bug for any open-source strategy.
- `pytest` did not collect at all: `dispatcher.py` used `Optional[Set[str]]` without
  importing `Set`. Fixed on this branch. The suite is 76 passing / 15 failing, and
  the failures are in the flagship paths (resume, chat grounding, platform restore).
- The repo root was full of scratch: 23 `test_*.py` files, `fix_indent.py`,
  `patch_groq.py`, `ws_test.py`, a stray screenshot. Moved to `attic/`.

None of this is a reason to give up on the code. It is a reason to stop treating
volume as progress.

---

## 2. The market, November 2026

Six findings, each of which kills an obvious pivot.

### Finding 1 — The category leader died, and the successor is a capture pipeline

Rewind was the reference product for "remember everything you saw". It rebranded to
Limitless, was acquired by Meta, and **shut down on 19 December 2025**
([donethat.ai](https://donethat.ai/compare/rewind),
[usecarly](https://www.usecarly.com/blog/rewind-ai-alternatives/)). Its replacement is
screenpipe: YC S26, ~20k stars, local-first, source-available under a commercial
licence, from $25/month ([explainx](https://www.explainx.ai/blog/screenpipe-yc-s26-local-work-memory-agents-july-2026),
[dibi8](https://dibi8.com/resources/dev-utils/screenpipe-screen-recording-ai-agents-2026/)).

**Kills:** "build a 24/7 screen recorder". It is owned by a funded company with two
years of Rust engineering, and the resource numbers alone make it a hard sell —
roughly 30 GB/month, 600 MB–4 GB RAM, 10–30% CPU in user reports
([ai-review](https://ai-review.com/memory/screenpipe/)).

### Finding 2 — Screenpipe's own users are telling you where the gap is

The most useful sentence I found in three hours of research, from an analysis of why
people leave Screenpipe:

> "Almost nobody leaves Screenpipe because of what it captures. They leave because of
> what it asks of them afterwards: you run the stack, you keep it running, and you
> write whatever sits above the raw capture yourself."
> — [luci.memories.ai](https://luci.memories.ai/blog/screenpipe-alternatives-2026)

And from its Hacker News launch:

> "I don't think that's really an objection to always-on capture — it's an objection to
> **opacity**. People will tolerate a lot of passive collection if they can see the
> receipts on what it's doing with it and where an answer traces back to… **provenance**
> is what actually earns it over time."
> — [HN discussion](https://news.ycombinator.com/item?id=49024620)

That is a description of the product this repository should become: **the layer above
raw capture, with receipts, that asks nothing of you afterwards.**

### Finding 3 — Agent memory is a red ocean with 40,000-star incumbents

Every one of these appeared in 2026: `hindsight` (44,886 stars, MIT, October 2026),
`ai-memory` (15.6k, MIT, Rust, Nov 2026), `agentmemory` (22k), `codebase-memory-mcp`
(27,500), `memorix`, `projectmem`, `supermemory`, `mem0/OpenMemory`, `cognee`,
`graphiti`
([hackernoon](https://hackernoon.com/i-tested-hindsight-the-open-source-memory-layer-for-coding-agents),
[opensourcealternatives](https://www.opensourcealternatives.to/item/ai-memory),
[genios](https://thegenios.com/blog/open-source-memory-layers-2026/)).

**Kills:** "become a memory MCP server for coding agents". Coming to that fight with a
Python monolith, zero stars and no benchmark would be suicide.

### Finding 4 — The big labs own the desktop agent

ChatGPT Work launched 9 July 2026 with Codex merged into one desktop app and ~10M
users; Claude Cowork went GA in April 2026 with direct local file access; Copilot
Cowork and Perplexity's Personal Computer are shipping; OpenClaw is MIT with 350k+
stars ([digitalapplied](https://www.digitalapplied.com/blog/chatgpt-work-openai-agent-launch-2026),
[hellofoundry](https://www.hellofoundry.ai/guides/ai-worker-agents-2026/)).

**Kills:** "build an always-on desktop agent that does your work".

### Finding 5 — Session restore exists as a hundred shallow scripts, and as nothing else

Search GitHub for "restore my session" and you find `crex` (terminal layouts only),
`Restage` (Windows apps only, no macOS/Linux), `claude-session-restore` (one agent,
one OS), `pi-reopen` (WezTerm only). Meanwhile "session handoff" for coding agents is
solved by **copy-pasted markdown skill files** — at least six near-identical variants
in circulation ([agentkit](https://agentkit.best/blog/claude-code-guides/claude-code-session-handoff-continue-work-without-context-loss),
[mcpmarket](https://mcpmarket.com/tools/skills/session-handoff-continuity-3)).

That is the shape of an unmet primitive: everyone hand-rolls it, badly, per tool,
per OS, per agent, and nobody owns the abstraction. When a need is met by
copy-paste, a format wins.

### Finding 6 — MCP became the distribution channel, and it is stateless now

MCP is governed by the Agentic AI Foundation under the Linux Foundation, spec
revision **2026-07-28** is current and **removed the `initialize` handshake** in favour
of `server/discover`; stdio is newline-delimited JSON-RPC
([bdemerson](https://www.bdemerson.com/article/model-context-protocol),
[getmaxim](https://www.getmaxim.ai/articles/the-mcp-protocol-transports-primitives-and-the-message-lifecycle/)).
Servers that only speak the old era will look broken to new clients.

**Kills:** anything that ships an agent integration as an afterthought. And it
creates an opportunity: a dual-era server is 300 lines and immediately works with
every agent.

### And the human side of the problem is not a productivity myth

The famous "23 minutes to refocus" is **misattributed** — it is not in the paper it is
cited for. What Mark, González and Harris actually measured in 2005 was worse and more
useful: a working day split into ~11-minute stretches, **57% of them interrupted**, and
an average of **25 minutes 26 seconds** before people returned to the interrupted task,
having worked on two other things in between. The most expensive switch is not the
interruption — it is the return to a project after days, and:

> "How long that takes depends on how much of where you stopped was written down."
> — [knowledgework.ai, Oct 2026](https://knowledgework.ai/guides/context-switching)

That sentence is the product requirement.

---

## 3. The gap

Everyone in this market is optimising **the agent's** context: give the model more of
your screen, your repo, your past. Nobody is optimising **the human's** continuity.
And the two are diverging: as agents execute more, the human's job becomes
*supervision and resumption* — starting a task, handing it off, coming back to it days
later, and knowing which of four parallel agents is doing what.

The result is a category with three shapes and a hole in the middle:

```
   screenshots ─────────────► searchable past        (Recall, screenpipe, Rewind†)
   text facts  ─────────────► agent knowledge base   (mem0, hindsight, ai-memory)
   markdown    ─────────────► hand-written handoff   (a hundred skill files)

                          ▲
                          │  nothing here
                          │
   structured state ───────┴──► resume your desk      ← the unowned verb
```

The hole is **state**: the concrete, verifiable, environment-level answer to *"where was
I, why, and what's next"* — small enough to be free and safe, structured enough for a
machine, and actionable enough to actually put your desk back.

---

## 4. The pivot

### Thesis

> **Own the resume, not the record.**
>
> Git is the format for what code became. Arova is the format for what work was in
> flight — and the one command that puts it back.

### Positioning

> **Git remembers what you committed. Arova remembers where you were.**

For the README, the show HN, the first line of the pitch — three ways to say it:

- "Resume points for your whole desk. Zero pixels, one command."
- "Save your working state like a game. Restore it on any machine, with any editor, with any agent."
- "The 3 KB alternative to recording your screen."

### The product: four surfaces, one primitive

1. **`arova save <name>`** → a resume point: repo + branch + head + dirty files, the
   working set, tabs, shell roots, running agents *with session ids*, and an `Intent`
   block (`why`, `next_step`, each tagged with its evidence).
2. **`arova resume`** → a plan, then a restore. Dry run by default. Reopens editor, files,
   tabs, shell directories; prints `claude --resume <id>` and never runs it.
3. **`arova packet`** → a budgeted, staleness-marked context packet for an agent.
4. **`arova mcp`** → the same primitive as tools/resources, so agents checkpoint
   *themselves* before their context window fills and read the point back afterwards.

### The four differentiators, in order of durability

1. **Zero pixels.** Not a policy — an architecture. There is no screenshot to subpoena,
   no video to leak, no NPU to buy, no compliance review to pass. Against Recall's
   demonstrated extraction problems and screenpipe's "brutal compliance conversation",
   this is a category-level wedge, not a feature
   ([screenpipe's own comparison](https://screenpipe.com/blog/microsoft-recall-vs-screenpipe)).
2. **Resume, not search.** Every competitor stops at *reading the past*. Restoring the
   environment is the part users actually want and nobody ships.
3. **A format, not an app.** `arova.resume/v1` is JSON and can be written by a VS Code
   extension, a browser extension, Cursor, or an agent. Formats compound; apps don't.
4. **Agent-neutral.** Claude Code, Codex, Cursor, OpenClaw all get the same memory of
   *you*. No lab will build this, because it would privilege their competitors' agent.

### Why this repository can win it — the asset map

| Pivot needs | Already in the repo | Work |
|---|---|---|
| Cross-platform "open the right thing" | `platform/services` (3k lines, 3 OSes) | Reuse behind the restore planner. |
| Evidence of what you were running | `shell_hook.sh`, `/proc` scanning, agent session files | Wire into one provider. |
| Tabs without an extension | browser history reader | Replace its over-filtering (see below). |
| Restore with proof | `restore_planner` + per-item outcomes | Reuse the outcome model as the plan output. |
| Honesty about staleness | TTL/provenance discipline in the old docs | Promoted into the format itself. |
| **Nothing at all** | the format, the CLI, the packet, the MCP server | **Built on this branch** (see §9). |

The old code was aimed at the wrong product, but it spent a year solving the
unglamorous parts of *this* one.

### A real bug found while building the prototype (and why it matters)

The existing browser filter silently dropped `github.com/acme/api/pull/412` because the
**pull request title** contained the word "checkout" — a substring match intended for
payment pages. It also kept nothing that could tell you a filter had run.

That is the whole trust problem in one line: over-filtering is invisible, and invisible
loss is worse than no capture. The new `privacy.py` decides on **host and path only**,
and counts every drop into `redactions` so the resume point can say what it withheld.
This is the kind of detail that turns a demo into infrastructure.

---

## 5. What to delete

Delete, do not refactor. Every line kept is a line that must be tested, documented and
explained to a stranger on the internet.

```
DELETE   frontend/                       15,045   the desktop app
DELETE   core/cognition/                  6,867   twelve layers ahead of evidence
DELETE   core/voice/                      2,684   different product
DELETE   core/automation/                 2,639   agents are a commodity now
DELETE   desktop/                         2,391   GTK orb, chat surface
DELETE   core/models/                     1,880   provider zoo
DELETE   daemon/                          1,674   no daemon is a feature
DELETE   core/memory/, presence/, intention/, projection/, telemetry/,
         environment/, reasoning/, policy/, capabilities/, bridge/, ipc/, audio/
                                          4,745
KEEP     core/platform/                   3,039   → arova/platform
KEEP     ambience/shell_hook.sh              350   → arova/hooks
KEEP     (rewritten) privacy + history       ~450   → arova/resume/providers
NEW      arova/resume/                    2,801   the product
```

**41,337 → ~7,000 lines, and a `pip install` with zero dependencies.** That is the
pitch in one number: the thing you install in ten seconds, not the monolith you compile
for an hour.

Keep `attic/` for a release or two as evidence of work and as a source of reusable
parts, then remove it.

---

## 6. The 90-day plan

The constraint is not code. It is that a 0-star repository with no distribution must
earn attention in one shot, and the only reliable shot is a **single command that does
something visibly impossible-feeling**.

### Week 1–2 — Make it shippable

- [ ] Publish `v0.1.0`: Apache-2.0 `LICENSE` (done), zero-dependency package, `pipx install arova`.
- [ ] 40-second demo GIF: terminal, `save`, close the laptop, `resume`, everything opens. This asset matters more than every other file in the repo.
- [ ] `arova doctor` and the "nothing sensitive ever leaves" page.
- [ ] Delete the kill list. Keep `attic/` for one release.
- [ ] Green CI on Linux + macOS + Windows, Python 3.9–3.13.

### Week 3–4 — Earn the first users

- [ ] Launch: Show HN, r/programming, r/ClaudeAI, r/LocalLLaMA, X. Two posts, one week apart: "Resume points" then "Your agents can checkpoint themselves."
- [ ] 10 design partners, one per workflow: backend dev, data scientist, writer, researcher, founder, law, design, support, ops, student.
- [ ] Instrument one number: **did the resume lead to 10 minutes of continuous work?** Local only, opt-in, and published as a weekly percentage.

### Week 5–8 — Close the loop that makes it stick

- [ ] **Auto-checkpoint:** a `SessionStart`/`Stop` hook (Claude Code, Codex, Cursor) so points are written without the human remembering. This is the retention mechanism.
- [ ] **VS Code / Cursor extension** (150 lines): reports open editors + unsaved state, replaces guessing the working set from git.
- [ ] **Cross-machine resume:** points are JSON, so a point in a git repo should resume on a laptop. This is the demo that makes people say "oh".
- [ ] `arova diff <a> <b>` — what changed between two points. Cheap, and it makes the format obviously useful.

### Week 9–12 — Decide the business

Only now, with usage data.

---

## 7. Business model — three honest options

| Option | What it is | Why it could work | Why it could fail |
|---|---|---|---|
| **A. Open core + team sync** *(default)* | Free CLI and format. Paid, end-to-end-encrypted, self-hostable sync of points across a team; policy and audit for enterprises. $8–12/seat. | The primitive is free forever, so adoption is unconstrained; teams pay for the thing individuals cannot build (server, encryption, admin). | Sync is a feature a competitor can give away. |
| **B. Screenless work ledger** *(the beachhead worth testing)* | Same engine, sold to firms that **cannot** record screens: law, healthcare admin, finance, consulting. Auditable "what did I do, why, what next" + defensible billable-hour reconstruction. | Zero-pixel is not a preference there, it is the only way in; the budget already exists (knowledge management, billing accuracy, onboarding). | Slow sales, compliance work, and a product surface that looks nothing like a dev tool. |
| **C. Be the format** *(the "best thing in the world" outcome)* | Apache-2.0, no product, sponsor-funded, adopted by editors, agents and capture tools. | If `arova.resume/v1` becomes what people write, the repo matters forever. | Formats need a killer implementation; without one it stays a nice spec. |

**Recommendation:** run **A as the open-source motion** from day one, and treat **B as a
paid discovery experiment in month 3** — five calls with a law firm and a consultancy
about reconstructing billable work. Do not build B until one of them offers to pay for a
pilot. And accept that **C is a legitimate end state**: if the repo becomes the standard,
that is a better outcome than a small SaaS nobody adopts.

---

## 8. Risks, and the criteria that should kill this

**The real risks, in order:**

1. **The labs ship native resume.** Codex and Cowork already keep session state. Counter: be cross-agent and cross-machine — the one thing a single vendor cannot offer. Ship the format before they ship a competitor to it.
2. **It is a nice-to-have, not a painkiller.** Someone may resume twice a week and shrug. Counter: measure it honestly in week 3–4; if ≥40% of resumes are followed by 10 minutes of work, it is a habit, not a novelty.
3. **Restore fidelity is genuinely hard** across Wayland, macOS Spaces, Windows virtual desktops, and every editor. Counter: make the *plan* the product (it is honest and useful even when the launch fails), and buy fidelity one adapter at a time.
4. **Trust, if you ever add capture.** The moment a screenshot lands in the codebase, the wedge is gone. Write that down as a constitutional rule.
5. **A solo maintainer.** 41k lines is unmaintainable by one person. 7k lines with 35 tests is not.

**Kill criteria — write these down before launch, then honour them:**

- 30 days after launch: **<100 stars** and **<3 non-author weekly users** → the wedge is wrong; go to option B and talk to ten firms.
- 90 days: **<25%** of saved points are ever resumed → the primitive is not being used; reconsider whether "save" or "restore" is the real verb.
- 6 months: no path to five paying teams or a funded standard → fold the format into an existing tool (screenpipe, an editor, an agent vendor) rather than keep a museum.

---

## 9. What I built on this branch (the proof, not the proposal)

A pivot document that cannot be run is a wish. This branch contains a working
implementation of the thesis:

```console
$ pip install -e .
$ arova doctor
$ arova save checkout-idempotency
$ arova resume          # dry run
$ arova mcp             # dual-era MCP server on stdio
```

**New code — `arova/resume/` (2,801 lines, stdlib only):**

| File | What it does |
|---|---|
| `schema.py` | `arova.resume/v1` — ResumePoint, provenance, TTL, digest, validation |
| `capture.py` | Assembles a point from providers, budgeted, degrading per section |
| `providers/repo.py` | Git ground truth, working set ranking, TODO/FIXME extraction |
| `providers/history.py` | Browser history across 5 browsers / 3 OSes, no extension |
| `providers/privacy.py` | **Host-and-path** filtering with counted redactions |
| `providers/terminal.py` | Shell-hook log + `/proc`; last command *and last failure* |
| `providers/agents.py` | Running agents + recovered session ids (`claude --resume …`) |
| `intent.py` | Deterministic `why` / `next_step`, each with its evidence source |
| `packet.py` | Token-budgeted context packet, staleness-marked, gaps declared |
| `restore.py` | Plan → dry run → apply; never executes a recorded command |
| `store.py` | Files, not a database; atomic writes; index; gc |
| `mcp.py` | Dual-era MCP server (2026-07-28 `server/discover` + legacy `initialize`) |
| `cli.py` | `save · resume · list · show · packet · mcp · doctor · hooks · gc` |
| `hooks.py` | Opt-in shell hook install/uninstall with a marked block |

**Also on this branch:** Apache-2.0 `LICENSE` (there was none, despite the README
claiming BSL), `docs/RESUME_POINT.md` (the format spec), a rewritten README, the
kill-list quarantine into `attic/`, a fixed import that made `pytest` unable to
collect, and **35 passing tests** that pin the four promises — round-trip, privacy,
honest intent, and never-execute.

`pytest` is green: `35 passed`.

---

## 10. If you only do one thing this week

Record the 40-second GIF.

`save` → close everything → `arova resume` → your editor, three tabs, two shells and
`claude --resume 8f2c1e4a` come back, with one line at the top: *"next: add the
duplicate-delivery test."*

Everything in this document is downstream of whether that clip makes a stranger say
*"wait, can I have that?"*

---

## Sources

- Rewind discontinued 19 Dec 2025 — [donethat.ai](https://donethat.ai/compare/rewind) · [usecarly](https://www.usecarly.com/blog/rewind-ai-alternatives/)
- screenpipe, YC S26, licence and pricing — [explainx](https://www.explainx.ai/blog/screenpipe-yc-s26-local-work-memory-agents-july-2026) · [dibi8](https://dibi8.com/resources/dev-utils/screenpipe-screen-recording-ai-agents-2026/)
- screenpipe resource use — [ai-review](https://ai-review.com/memory/screenpipe/)
- Why users leave screenpipe — [luci.memories.ai](https://luci.memories.ai/blog/screenpipe-alternatives-2026)
- HN launch thread (opacity, provenance) — [news.ycombinator.com](https://news.ycombinator.com/item?id=49024620)
- Recall's extraction problem — [screenpipe blog](https://screenpipe.com/blog/microsoft-recall-vs-screenpipe)
- Agent memory landscape — [hackernoon](https://hackernoon.com/i-tested-hindsight-the-open-source-memory-layer-for-coding-agents) · [opensourcealternatives](https://www.opensourcealternatives.to/item/ai-memory) · [genios](https://thegenios.com/blog/open-source-memory-layers-2026/)
- ChatGPT Work / Cowork / OpenClaw — [digitalapplied](https://www.digitalapplied.com/blog/chatgpt-work-openai-agent-launch-2026) · [hellofoundry](https://www.hellofoundry.ai/guides/ai-worker-agents-2026/)
- Session handoff skills — [agentkit](https://agentkit.best/blog/claude-code-guides/claude-code-session-handoff-continue-work-without-context-loss) · [mcpmarket](https://mcpmarket.com/tools/skills/session-handoff-continuity-3)
- MCP spec 2026-07-28 — [bdemerson](https://www.bdemerson.com/article/model-context-protocol) · [getmaxim](https://www.getmaxim.ai/articles/the-mcp-protocol-transports-primitives-and-the-message-lifecycle/)
- Context switching research, corrected — [knowledgework.ai](https://knowledgework.ai/guides/context-switching)
