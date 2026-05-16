# dotagent

> **One `.agent/` folder. Every AI coding tool in sync.**
> Bug registry, anti-patterns, DB hotspots, Redis keys, dependency map — every AI
> agent on your team reads the same canonical context, ranked by severity, every
> session, automatically. Plus a built-in project-management layer that tracks
> modules through a dev ↔ QA cycle with mandatory rationale on every decision.

[![ci](https://github.com/dilawarabbas1/dotagent/actions/workflows/ci.yml/badge.svg)](https://github.com/dilawarabbas1/dotagent/actions/workflows/ci.yml)
&nbsp;
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
&nbsp;
Python 3.11+

---

## Why

Every AI coding agent — Claude Code, Cursor, GitHub Copilot, OpenCode — reads
its own config file (CLAUDE.md, .cursorrules, .github/copilot-instructions.md,
AGENTS.md). You end up maintaining the same project context in four places,
or worse, you don't, and your agents work cold every session.

dotagent fixes that. Your `docs/` directory is the single source of truth.
dotagent indexes it, merges with four kinds of memory (working / episodic /
semantic / personal), and renders the right config for every tool. Edit one
file in `docs/`, run `dotagent sync`, every agent across every dev's machine
picks it up.

It's also a multi-developer + multi-AI-tool attribution system: every Edit,
Save, and commit is recorded with `actor` (the human) and `tool` (the AI)
fields. `dotagent who --file path/to/file` tells you which teammate touched
it with which AI agent.

And it's a project manager: define modules through an interactive Q&A,
track them through a dev → QA cycle where documents wire the handoff in
both directions, and ship only when QA passes with a written rationale.

---

## Quickstart — 30 seconds

```bash
pipx install "git+https://github.com/dilawarabbas1/dotagent"
cd ~/code/your-repo
dotagent init               # zero prompts; scans, scaffolds .agent/, indexes docs/, renders CLAUDE.md
dotagent doctor             # self-check
```

Open Claude Code (or Cursor, or VS Code with Copilot) in that repo. The
generated `CLAUDE.md` (or `.cursorrules` / `.github/copilot-instructions.md`)
now contains:

- Top-N bugs from `docs/bug-registry.md`, severity-ranked
- Anti-patterns to avoid
- Database tables/columns to handle with care
- Redis key conventions
- Service dependency map
- Architecture section index
- Your personal style preferences (never leaks to teammates)
- Current branch + recent files you've touched
- Recent team activity filtered to those files
- A footer pointing back to every `docs/*.md` source

When you commit, the install hook adds a
`Co-authored-by: dotagent <... actor=alice tool=claude_code>` trailer.
Attribution survives in `git log` even on machines without dotagent.

---

## What you actually edit

dotagent is opinionated about *one* thing: **`docs/` is the source of truth**.
It never writes there. The hierarchy:

```
your-repo/
├── docs/                            ← YOU edit these. dotagent indexes.
│   ├── bug-registry.md
│   ├── anti-patterns.md
│   ├── redis-key-registry.md
│   ├── db-impact-map.md
│   ├── dependency-map.md
│   └── architecture.md
└── .agent/                          ← dotagent generates / manages
    ├── config.yaml                  ← points at docs/ files above
    ├── style.md rules.md ...        ← five project-wide source files
    ├── memory/                      ← four memories (see below)
    ├── skills/ tools/               ← prompts the AI runtime uses
    └── .cache/                      ← gitignored; regenerated on sync
```

Plus what dotagent emits for each AI tool:

```
your-repo/
├── CLAUDE.md                            ← Claude Code reads this
├── .cursorrules                         ← Cursor reads this
├── .github/copilot-instructions.md      ← GitHub Copilot reads this
└── AGENTS.md                            ← OpenCode reads this
```

Don't hand-edit those four — they're regenerated. Edit `docs/*.md` or
`.agent/*.md` and run `dotagent sync`.

See [`examples/`](examples/) for a working sample of the `docs/` format.

---

## The four memories

| Memory | When | Stored at | Shared? |
|---|---|---|---|
| **Working** | now (current session) | `.agent/memory/working/<actor>/current.json` | local only |
| **Episodic** | before (every event) | `.agent/memory/episodic/YYYY/MM/DD/<actor>__<session>.jsonl` | committed (zero merge conflicts by design) |
| **Semantic** | patterns & rules | `.agent/memory/semantic/{rules,patterns}/.../<sha>-<slug>.md` | committed (content-hashed slugs prevent collisions) |
| **Personal** | per-actor style | `.agent/memory/personal/<actor>/profile.yaml` | per-actor, **never merged into other devs' generated configs** |

Every recorded event has `actor`, `tool`, `host`, `session` fields. Two
teammates can write to the same file on the same day without conflicts
because filenames namespace by actor + session.

---

## Day-to-day commands

```bash
# core
dotagent status                       # what dotagent knows about this repo
dotagent context                      # exactly what an AI agent sees
dotagent context --format markdown    # full body, for piping/inspection
dotagent sync                         # rebuild adapters from docs/ + .agent/
dotagent sync --dry-run               # unified diff of what would change
dotagent doctor                       # self-check; nonzero exit on fail

# visibility (Phase 2)
dotagent who --file path/to/file.py   # which devs / AI tools touched it
dotagent timeline path/to/file.py     # edit history
dotagent activity --since 7d --by alice --tool claude_code
dotagent feed --limit 50              # team-wide stream
dotagent leaderboard --since 30d

# tools (Phase 4)
dotagent tool debug "<stack trace>"   # match against bugs + past failures
dotagent tool checklist --since 14d   # pre-deploy gate
dotagent tool memory "BUG-001"        # search the four memories
dotagent tool pattern-extractor --write

# skills (Phase 3) — needs ANTHROPIC_API_KEY for real runs
dotagent skill list
dotagent skill run plan --task "ship JWT rotation"
dotagent skill pipeline observer plan code review --task "ship X"

# auto-dream (Phase 5)
dotagent dream run --since 30d        # extract signals → candidates
dotagent dream list                   # pending candidates
dotagent dream graduate <id> --rationale "..."   # rationale REQUIRED
dotagent dream reject   <id> --rationale "..."   # rationale REQUIRED
dotagent dream cron-install           # daily 02:00 UTC
dotagent dream github-action          # write nightly PR workflow

# bridging tools without native hooks
dotagent watch cursor                 # foreground watcher (Cursor < 0.40)
dotagent serve --host 0.0.0.0 --port 9700   # team event server

# project management (Phase 8)
dotagent project init                          # interactive scope-builder Q&A
dotagent project add-module "<name>"           # per-module Q&A with vagueness probes
dotagent project status                        # source-of-truth completion %
dotagent project start <id>                    # open a dev cycle
dotagent project handoff <id>                  # writes the QA handoff doc
dotagent project qa-record <id> --result pass|fail --rationale "..."  # rationale REQUIRED
dotagent project resolve <id>                  # ship after qa_passed
dotagent project next                          # dep-aware "what's next"
```

---

## Project management — track modules end-to-end

Big projects break down into modules. dotagent's `project` layer builds an
extensive per-module plan via interactive Q&A, then tracks each module
through a dev ↔ QA cycle until ship.

The trick: **documents wire the handoff in both directions.**

```
1. dotagent project add-module "Auth"          → interactive Q&A builds PLAN.md
2. dotagent project start 01-auth              → cycle 1 opens
3. ... dev work ...
4. dotagent project handoff 01-auth            → writes cycles/01/dev-handoff.md
                                                 (QA tool reads this)
5. dotagent project qa-record 01-auth          → if FAIL: writes qa-findings.md
        --result fail --rationale "..."          (dev tool reads this next round)
6. dotagent project start 01-auth              → cycle 2 opens automatically
7. ... dev fixes ...
8. dotagent project handoff 01-auth            → cycles/02/dev-handoff.md
9. dotagent project qa-record --result pass --rationale "..."
10. dotagent project resolve 01-auth           → SHIPPED; completion.md written
```

Whichever tool you open (Claude Code, Codex, Cursor, ...) the rendered
`CLAUDE.md` automatically points at the right document for the current
state — `PLAN.md` while developing, `qa-findings.md` after a fail,
`dev-handoff.md` when the QA tool is up. **No context loss between rounds.**

Rationale on `qa-record` is mandatory (the audit of what passed and why).
The scope-builder also detects vague answers and probes for specifics
(hedge words like *maybe*, vague quantifiers like *fast* without numbers).

`dotagent project status` aggregates module states across the project:

```
$ dotagent project status
project:  TestPortal
modules:  2/3 shipped  (67% complete)
  shipped:        01-config, 02-auth
  in_progress:    03-payments
  planned:        04-notifications
```

That's the source of truth. See the wiki page
[**Project Management**](https://github.com/dilawarabbas1/dotagent/wiki/Project-Management)
for the full workflow.

---

## How dotagent compares

|                                   | Claude `CLAUDE.md` | Cursor Rules | Copilot custom instr. | dotagent |
|-----------------------------------|--------------------|--------------|------------------------|----------|
| One file per tool                 | yes                | yes          | yes                    | **one source, every tool** |
| Reads your `docs/`                | no                 | no           | no                     | **yes (configurable)** |
| Embeds bug registry / anti-patterns | manual           | manual       | manual                 | **automatic, severity-ranked** |
| Per-developer personalization     | no                 | no           | no                     | **per-actor profile** |
| Attribution surviving in git log  | no                 | no           | no                     | **`Co-authored-by` trailer** |
| Stack-trace → past failures lookup | no                | no           | no                     | **`dotagent tool debug`** |
| Auto-learn from team experience   | no                 | no           | no                     | **Auto-Dream with mandatory rationale** |
| Track modules through dev ↔ QA cycle | no              | no           | no                     | **`dotagent project` with mandatory QA rationale** |

---

## Migrating an existing Claude-Code-Optimization repo

If your project already has `docs/bug-registry.md`, `docs/anti-patterns.md`,
`prompts/*.md`, and `.claude/hooks/*.sh`:

```bash
cd ~/code/your-cco-project
pipx install "git+https://github.com/dilawarabbas1/dotagent"
dotagent init --no-llm
dotagent migrate-cco       # wires docs/ as sources, imports prompts/ → .agent/skills/
dotagent sync
```

Nothing under `docs/` is copied. `prompts/*.md` become
`.agent/skills/imported-<slug>.md`. Your existing `CLAUDE.md` content gets
parsed and routed into `.agent/{style,rules,architecture,patterns,preferences}.md`
so hand-written copy survives.

---

## Optional extras

```bash
pip install 'dotagent[ml]'         # sentence-transformers + sklearn → semantic clustering for Auto-Dream
pip install 'dotagent[server]'     # FastAPI + uvicorn → `dotagent serve`
pip install 'dotagent[watch]'      # watchdog → `dotagent watch cursor`
pip install 'dotagent[all]'        # everything above
```

The base install stays small (~5 MB; click + PyYAML + Jinja2 + anthropic).
Extras only pull in their deps when needed.

---

## Architecture in one diagram

```
docs/*.md  ─────────────────────┐
(your hand-written truth)       │
                                ▼
            ┌─────────────────────────────────┐
            │   Source Indexer (sources.py)   │
            └─────────────┬───────────────────┘
                          │ structured entries
                          ▼
.agent/*.md ──┐  ┌───────────────────┐  ┌── memory/working   (now)
              ├─▶│  Context Resolver │◀─┼── memory/episodic  (before)
config.yaml ──┘  │   (context.py)    │  ├── memory/semantic  (patterns + indexed sources)
                 └─────────┬─────────┘  └── memory/personal  (per-actor)
                           │ merged Context object
                           ▼
                ┌──────────────────────┐
                │  Adapters (render)   │
                │  CLAUDE.md, .cursor- │
                │  rules, copilot, ... │
                └──────────┬───────────┘
                           ▼
       AI agent reads CLAUDE.md and gets the full context.
```

---

## Documentation

- [`USING_WITH_CLAUDE_CODE.md`](USING_WITH_CLAUDE_CODE.md) — practical guide
- [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) — architecture decisions + roadmap state
- [`CHANGELOG.md`](CHANGELOG.md) — what changed when
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute
- [`examples/`](examples/) — sample `docs/*.md` showing the expected format
- **[Wiki](https://github.com/dilawarabbas1/dotagent/wiki)** — Getting Started, Architecture, Memory Model, Sources & Docs, Auto-Dream, Project Management, Server & RBAC, Multi-Project & Multi-Developer, Migrating from CCO, Troubleshooting, FAQ

---

## Troubleshooting

```bash
dotagent doctor                  # first line of defense — covers 90% of issues
DOTAGENT_DEBUG=1 dotagent sync   # surface silenced exceptions to stderr
```

Common failure modes and fixes are in
[`USING_WITH_CLAUDE_CODE.md#quick-troubleshooting`](USING_WITH_CLAUDE_CODE.md#quick-troubleshooting).

---

## Status

**v0.2.0 — launch-ready** with project management. 102 tests passing across
all phases. Live-tested end-to-end (interactive Q&A, real git diff, full
dev↔QA cycle, multi-module dep resolution, backup/restore, server over HTTP).
Not yet on PyPI (install via git URL works); not yet on the VS Code
Marketplace (build the `.vsix` from `extensions/vscode-copilot/`). Both are
convenience-only and don't block use.

See [`CHANGELOG.md`](CHANGELOG.md) for full release notes.

---

## License

MIT. See [`LICENSE`](LICENSE).
