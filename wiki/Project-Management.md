# Project Management

dotagent includes a full project-management layer for tracking large
multi-module work end-to-end. You define modules, dotagent builds an
extensive plan through an interactive Q&A, and a dev ↔ QA cycle keeps
work moving with documents wiring the loop.

The data lives in `.agent/project/`. The CLI is `dotagent project ...`.

## Conceptual model

```
PROJECT
├── scope (name, goal, out-of-scope, success criteria, tool routing)
└── MODULES (functional units, shipped one at a time)
    ├── plan (purpose, acceptance criteria, deps, technical approach, risks)
    └── CYCLES (one per dev → QA round)
        ├── dev-handoff.md     ← dev says "done" — QA tool reads this
        └── qa-findings.md     ← QA writes findings — dev tool reads this
```

A module is `shipped` only when:
1. The latest cycle's QA result is `pass`, AND
2. You explicitly run `dotagent project resolve <module>`.

`dotagent project status` aggregates module states. That's the source of
truth for project completion.

## The dev ↔ QA loop

Two tools, talking through markdown files dotagent generates:

```
  ┌─────────────────────────┐                  ┌─────────────────────────┐
  │  Development tool       │                  │  QA tool                │
  │  (e.g., Claude Code,    │                  │  (e.g., Claude Code     │
  │   Codex, Cursor)        │                  │   with QA prompt)       │
  └──────────┬──────────────┘                  └──────────┬──────────────┘
             │                                            │
             │ writes code                                │
             │                                            │
             ▼                                            │
  $ dotagent project handoff <id>                         │
             │                                            │
             │ writes:                                    │
             │   cycles/01/dev-handoff.md  ──────────────▶│ reads
             │   (includes QA prompt at bottom)           │
             │                                            │ runs QA
             │                                            │
             │ reads:    qa-findings.md  ◀────────────────│ writes
             │                                            │
             ▼                                            ▼
  $ dotagent project qa-record <id>           (cycle complete; module is
        --result pass|fail                     either ready to ship or
        --rationale "..."                      back to dev for cycle N+1)
```

The trick: **CLAUDE.md / .cursorrules / etc. always surface the right
document for the current state.**

- When state is `IN_PROGRESS` and the previous cycle's QA failed →
  CLAUDE.md tells your dev tool *"read `cycles/<N>/qa-findings.md` — these
  findings are what you need to address before the next handoff."*
- When state is `DEV_COMPLETE` → CLAUDE.md tells your QA tool *"read
  `cycles/<N>/dev-handoff.md` and follow the QA prompt at the bottom."*
- When state is `QA_PASSED` → CLAUDE.md tells you *"the module is ready
  to ship — verify and run `dotagent project resolve`."*

So whichever tool you open, the AI agent always knows which document to
read and where in the workflow you are.

## Module lifecycle (state machine)

```
   defined ─→ planned ─→ in_progress ─→ dev_complete ─→ qa_passed ─→ shipped
                            ▲                │
                            └────────────────┘
                              qa-fail loops back
                              into a new cycle
```

Plus a sideband `blocked` state reachable from any active state; `unblock`
restores the previous state.

## End-to-end example

```bash
# Once per project:
dotagent project init
  → asks: project name, goal, out-of-scope, success criteria,
          stakeholders, constraints, dev tool/model, qa tool/model
  → writes: .agent/project/plan.yaml, .agent/project/SCOPE.md

# Per module (Q&A builds the extensive plan):
dotagent project add-module "Auth Service"
  → asks: purpose, in-scope, out-of-scope, acceptance criteria (numbered),
          dependencies on other modules, technical approach, risks, effort
  → writes: .agent/project/modules/01-auth-service/{module.yaml, PLAN.md}
  → state: planned

# Start dev:
dotagent project start 01-auth-service
  → state: in_progress (cycle 1)
  → working-memory task updated; AI tool sees the active module in CLAUDE.md

# (write code, commit, etc. The post-tool/post-commit hooks log events.)

# Dev says "done":
dotagent project handoff 01-auth-service --notes "watch the rotation case"
  → state: dev_complete (cycle 1)
  → writes: cycles/01/dev-handoff.md (with embedded QA prompt)

# QA tool's CLAUDE.md now points at cycles/01/dev-handoff.md
# QA runs, writes its findings to cycles/01/qa-findings.md, then:

dotagent project qa-record 01-auth-service --result fail \
    --rationale "rotation edge case fails under load"
  → state: in_progress (back to dev, cycle 1's qa_result is recorded)
  → dev tool's CLAUDE.md now points at cycles/01/qa-findings.md

# Dev fixes:
dotagent project start 01-auth-service       # opens cycle 2
# ... dev work, commits ...
dotagent project handoff 01-auth-service --notes "addressed under load"
  → state: dev_complete (cycle 2)
  → writes: cycles/02/dev-handoff.md

# QA re-runs (now on cycle 2's handoff):
dotagent project qa-record 01-auth-service --result pass \
    --rationale "all acceptance criteria met under load"
  → state: qa_passed

# Ship:
dotagent project resolve 01-auth-service --rationale "v0.1 release"
  → state: shipped
  → writes: completion.md (audit of all cycles)
```

## Rationale is mandatory on `qa-record`

Same rule as Auto-Dream graduations. Without a written reason, you'd never
know six months later why a module shipped with the issues it had, or
why a fix-cycle was rejected. The rationale is the audit trail.

```bash
$ dotagent project qa-record 01-auth-service --result pass
Error: Missing option '--rationale'

$ dotagent project qa-record 01-auth-service --result pass --rationale ""
Error: rationale is required (pass or fail) — non-negotiable
```

## Smart Q&A — clearing ambiguity

The scope builder runs every answer through two layers:

1. **Heuristic checks** (always on):
   - Hedge words (*maybe, probably, kind of, some*) trigger a follow-up.
   - Single-word answers to open questions trigger a follow-up.
   - Vague quantifiers (*fast, scalable, robust*) without numbers trigger
     a "can you give a measurable target?" follow-up.

2. **LLM probe** (when `ANTHROPIC_API_KEY` is set):
   - Runs the question + answer through the model with a strict-JSON
     classifier prompt: `{clear: bool, followup: "..."}`.
   - Surfaces a model-suggested follow-up if the answer is judged vague
     or inconsistent.

You can always **press Enter to accept** your current answer if you
disagree with the probe. Type `<EDITOR>` in any answer to open `$EDITOR`
for long-form input.

## Tool routing

`.agent/project/plan.yaml` records per-role tool/model defaults:

```yaml
tools:
  development:
    tool: claude_code      # or codex, cursor, copilot, opencode, custom
    model: claude-opus-4-7
  qa:
    tool: claude_code
    model: claude-sonnet-4-6
  review:
    tool: claude_code
    model: ''
  planning:
    tool: claude_code
    model: ''
```

The dev-handoff document embeds the *configured QA tool* so whoever runs
QA knows the intended setup. Per-module overrides go in `module.yaml`'s
`tools:` block if a specific module needs a different tool.

## Project context flows into every CLAUDE.md

When you run `dotagent sync`, every adapter output (CLAUDE.md, .cursorrules,
.github/copilot-instructions.md, AGENTS.md) gets a `## Project:` section:

```markdown
## Project: `AI Portal`

_Goal:_ Ship the new self-serve portal

**Progress:** 2/5 modules shipped (40%)
- ★ shipped:      01-config, 02-logging
- ▶ in_progress:  03-auth-service
- ○ planned:      04-rate-limiter, 05-payments

### → Active module: `03-auth-service` (in_progress)
_Issue and verify JWTs_

**Acceptance criteria:**
- [ ] POST /auth/login issues a valid JWT
- [ ] JWT verifies against the documented public key
- [ ] Stale JWTs (>30s after rotation) are rejected
- [ ] Rate-limited to 10 req/min per IP

**Read next:** `.agent/project/modules/03-auth-service/PLAN.md` — _the module plan you're building against_
```

After a qa-fail, the **Read next** line points at the qa-findings doc —
so your dev tool picks up exactly where QA left off, no context loss.

## Commands cheat-sheet

```bash
dotagent project init                       # one-time project scope Q&A
dotagent project add-module "<name>"        # per-module Q&A (extensive plan)
dotagent project list                       # all modules + states
dotagent project status                     # progress + next recommended
dotagent project show <id>                  # detail incl. cycle history
dotagent project next                       # recommend the next module (resolves deps)

dotagent project start <id>                 # open a cycle, set task in working memory
dotagent project handoff <id> [--notes "...]  # dev → QA: write the handoff doc
dotagent project qa-prompt <id>             # print the QA prompt for piping
dotagent project qa-record <id> --result pass|fail --rationale "..."  [--findings-file path]
dotagent project resolve <id> [--rationale "..."]   # qa_passed → shipped

dotagent project block <id> --reason "..."  # sideband: blocked
dotagent project unblock <id>               # restore previous state
```

## Where everything lives

```
.agent/project/
├── plan.yaml                       ← source of truth (project-level)
├── SCOPE.md                        ← human-readable scope (regenerated)
├── tools.yaml                      ← (reserved for future per-role overrides)
└── modules/
    └── <id>/
        ├── module.yaml             ← source of truth (per-module state + plan)
        ├── PLAN.md                 ← human-readable plan from Q&A
        ├── completion.md           ← written on `resolve` (cycle audit)
        └── cycles/
            ├── 01/
            │   ├── dev-handoff.md  ← dev → QA for cycle 1
            │   ├── qa-findings.md  ← QA → dev for cycle 1 (only if qa-fail)
            │   └── files-changed.txt
            ├── 02/
            │   └── ...
            └── ...
```

`plan.yaml` and `module.yaml` are the canonical state. The markdown files
are regenerated from them.

## Next

- **[[Auto-Dream]]** — qa-fail events flow into episodic memory automatically;
  Auto-Dream picks up recurring fail patterns and proposes graduations.
- **[[Memory Model]]** — how project events integrate with the four memories.
- **[[Commands Reference]]** — every project subcommand with options.
