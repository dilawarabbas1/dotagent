# CLAUDE.md design — what we define and why

_Status: locked as of v0.5.0 · last updated 2026-05-20_

This document explains the **design philosophy, structure, and rationale**
behind dotagent's CLAUDE.md (and its sister adapter files: `.cursorrules`,
`.github/copilot-instructions.md`, `AGENTS.md`). It is the canonical
reference for anyone modifying the renderer, extending the canonical
schema, or wondering "why does CLAUDE.md look like that?"

For the *user-facing* explanation of how each file in a dotagent project
behaves, see `README.md` and `CODA_PROMPT.md`. For the *implementation*,
see `src/dotagent/render/manifest.py` and `src/dotagent/canonical_structure.py`.

---

## TL;DR

CLAUDE.md is a **navigation manifest**, not a content compendium.

- **v1 (pre-0.5.0)** stuffed every doc's content inline — bug-registry top-N,
  anti-patterns top-N, architecture sections, brief excerpts, all in one
  file. Worked for small projects; broke at scale (50K–100K tokens for a
  real multi-service project).

- **v3 (0.5.0+)** keeps CLAUDE.md to ~3K tokens with one-line pointers to
  source files. The AI uses its file-read tools to chase pointers as
  needed. 97% token reduction; sharper content; zero duplication.

The change is possible because modern AI coding tools (Claude Code,
Cursor 0.40+, Copilot, OpenCode) all have file-read tools. They don't
need everything embedded upfront.

---

## What CLAUDE.md IS

A four-layer document that gives an AI agent everything it needs to
work safely and well in this project:

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1 — How to read this file       (the reading protocol)   │
│  Layer 2 — Workflow contract           (before/during/after)    │
│  Layer 3 — Hard policy                 (never-violate list)     │
│  Layer 4 — Navigation manifest         (where-to-find-what)     │
└─────────────────────────────────────────────────────────────────┘
```

Layers 1–3 are **invariant** across all dotagent projects (with
project-specific placeholders like `{meta_branch}` filled in).
Layer 4 is **project-specific** (driven by the canonical schema).

## What CLAUDE.md IS NOT

- **Not the brief.** The brief lives at `.agent/project_brief.md`. CLAUDE.md
  links to it; doesn't embed it.
- **Not the plan.** The plan lives at `.agent/project/plan.yaml` + `SCOPE.md`.
- **Not the bug registry.** That lives at `docs/bug-registry.md`.
- **Not the architecture doc.** That lives at `docs/architecture.md`.
- **Not "what the AI sees."** The AI sees CLAUDE.md *plus* every file
  CLAUDE.md points to, read on demand. CLAUDE.md is the index, not the catalog.

---

## Why we went from compendium → manifest

The original design (v0.1 through 0.4) was a dense compendium because:

1. **Early AI tools couldn't read files on demand.** Claude pre-Read-tool
   had to be handed everything in the system prompt. So we embedded
   bug-registry, architecture, anti-patterns — everything — into CLAUDE.md.
2. **There was no schema enforcement.** Each adapter renderer had its
   own ad-hoc sections. Drift was easy.
3. **Token budgets were small.** Context windows were 8K–32K. Selective
   embedding was less effective than just rendering everything.

By v0.4, three things had changed:

1. **Modern AI tools have file-read tools.** Claude Code's `Read`, Cursor
   0.40+'s file-system access, Copilot's workspace tools. Pointers work.
2. **Real projects scaled past CLAUDE.md.** Aigent's CLAUDE.md hit 50K
   tokens, leaving only half the context window for actual work.
3. **The dev↔QA cycle made discipline matter.** Without a workflow
   contract embedded at the top of CLAUDE.md, AI agents were skipping
   doc updates, pushing without QA, etc.

The redesign addresses all three.

---

## The four layers

### Layer 1 — How to read this file (the reading protocol)

```
1. Read this entire CLAUDE.md (you are here)
2. Read EVERY file listed under "🔴 MUST READ" below
3. Read CLAUDE.local.md if it exists (your per-session sidecar; gitignored)
4. Read .agent/git.md to understand branch rules + push policy
5. Identify what you've been asked to do, then jump to the matching
   "Where to find what" section — follow pointers as needed.
```

**Why first?** Without this, AI agents skip ahead to "the part I need"
and miss critical context. Numbered protocols are reliably followed.

**Invariant** across projects — same text everywhere, no placeholders.

### Layer 2 — Workflow contract

The before/during/after lifecycle with the explicit **OWNERSHIP RULE**:

```
• dotagent writes GENERATED files (CLAUDE.md, SCOPE.md, CONTRACTS.md,
  git.md, the brief's Modules table). You never edit these.

• YOU (Claude) write CONTENT files:
    - docs/*.md (bug-registry, anti-patterns, redis-keys, db-impact-map,
      dependency-map, architecture) — these are the project's truth;
      dotagent never writes here. Keeping them current is YOUR job.
    - Cycle artifacts (contract.md, dev-handoff.md, qa-findings.md) —
      you write through dotagent CLI commands.
```

The ownership rule is the load-bearing sentence of the entire design.
Every doc has exactly one writer; no ambiguity about who updates what.

Then four sub-sections:

- **BEFORE coding** — confirm frozen contract exists; re-read scope.
- **DURING coding** — stay within scope; cite FEAT-NN; never silently
  bypass rules.
- **AFTER coding — MANDATORY documentation updates** — the checklist
  Claude runs through before handoff. Eight items, all framed as
  "**YOU** edit `docs/X.md`" so ownership is unambiguous.
- **HANDOFF → WAIT for QA → ONLY ON pass → push** — the QA-gated git
  workflow. Push only after `qa-record --result pass`; read `git.md`
  before push; never `--no-verify`.

**Why this works**: It's a checklist embedded in the file the AI reads
first, with explicit ownership and exact commands. The AI has no excuse
for "I didn't know I needed to update bug-registry."

**The honest gap**: post-task hygiene is behavioral. dotagent can't yet
enforce "you touched auth.py but didn't update bug-registry." We rely
on the AI reading the checklist + having it fresh in working memory.
Future enforcement (v0.6+): post-commit hooks that flag drift.

### Layer 3 — Hard policy (never-violate list)

```
✗ NEVER push code to a meta branch (see .agent/git.md).
✗ NEVER push without QA-pass recorded via dotagent project qa-record.
✗ NEVER use git push --no-verify to bypass the dotagent pre-push hook.
✗ NEVER hand-edit a file with a <!-- generated by dotagent --> banner.
✗ NEVER graduate a semantic rule without --rationale "...".
✗ NEVER record qa-record --result pass without --rationale "...".
✗ NEVER freeze a contract without convergence (unless --force + rationale).
✗ NEVER edit contract.frozen.md — it's immutable.
✗ NEVER skip the post-task doc-update checklist.
```

Why a separate section instead of inline in the workflow contract?
Because some "NEVER" items are general (never edit generated files)
and apply across all tasks, not just code changes.

Half of these are **machine-enforced** (dotagent CLI refuses without
the right flags). The other half are **policy** that an AI agent can
technically violate but absolutely shouldn't.

### Layer 4 — Navigation manifest (where-to-find-what)

This is the schema-driven section. Each entry in
`canonical_structure.py` is grouped into a category, and each
category becomes a section in CLAUDE.md with bullet points like:

```markdown
## 🎯 Business intent

- `.agent/project_brief.md` — Business intent: OBJ-NN, FEAT-NN, RULE-NN,
  vision, non-goals.

## 📋 What's planned

- `.agent/project/plan.yaml` — Machine-readable plan: FEAT→Module mapping,
  repos manifest.
- `.agent/project/SCOPE.md` — Project blueprint: modules, success criteria,
  scope.

[... and so on for every category ...]
```

The AI reads pointers; it reads source files when its task requires them.
A bug-fix session jumps to "🐛 Bug-fix lookups." A design session jumps
to "🏗️ Technical architecture." No wasted tokens on irrelevant
sections.

---

## The schema-driven approach

The core architectural decision: **CLAUDE.md's navigation manifest is
not hand-written. It is derived from the canonical schema in
`canonical_structure.py`.**

### Why schema-driven

Three problems hand-written rendering had:

1. **Drift.** Add a new doc → forget to update CLAUDE.md → AI never
   learns the doc exists. Schema-driven means adding a `SchemaEntry`
   automatically produces a pointer.
2. **No tier-awareness.** project-root, service-repo, and single-repo
   should each show different files. Hand-coding three renderers is
   bug-prone.
3. **No coverage proof.** Hand-written sections might omit a file by
   accident, undiscovered until someone notices CLAUDE.md doesn't
   mention it.

Schema-driven solves all three:

```python
# Adding a new file = one new SchemaEntry
SchemaEntry(
    path="docs/new-thing.md",
    required=False,
    kind=KIND_FILE,
    category=CAT_ARCHITECTURE,
    when_to_read="The new thing's spec. YOU update when X changes.",
)
```

That's it. CLAUDE.md auto-includes the pointer on next render.
Coverage tests prove the new file is reachable.

### Categories

23 explicit categories cover every reasonable use. Sample:

| Category | CLAUDE.md section | Example entries |
|---|---|---|
| `CAT_MUST_READ` | 🔴 MUST READ before any code edit | project_brief, rules, NOW.md, git.md |
| `CAT_PROJECT_PLAN` | 📋 What's planned | plan.yaml, SCOPE.md |
| `CAT_CONTRACTS` | 📜 Active contracts + cycles | modules/, cycle artifacts |
| `CAT_ARCHITECTURE` | 🏗️ Technical architecture | architecture.md (×2), dependency-map.md |
| `CAT_BUGS` | 🐛 Bug-fix lookups | bug-registry.md |
| `CAT_DATA_LAYER` | 🗄️ Data layer | db-impact-map.md, redis-keys.md |
| `CAT_MEMORY_*` | 🧠 Memory layers | working/, episodic/, semantic/, personal/ |
| `CAT_DREAM` | 💭 Auto-Dream | dream/candidates/, dream/graduated/ |
| `CAT_HIDDEN` | (suppressed) | .version, .imported/, .cache/ |

Every `SchemaEntry` declares its category. The default is
`CAT_UNCATEGORIZED` — and a coverage test fails CI if any entry remains
there. Forces explicit categorization.

### Coverage guarantees

Three tests in `tests/render/test_manifest_coverage.py` make the design
robust:

1. **`test_every_schema_entry_has_a_category`** — no entry may default
   to `CAT_UNCATEGORIZED`. Forces every new doc to declare its
   placement.
2. **`test_every_non_hidden_entry_appears_in_manifest`** — every entry
   not marked `CAT_HIDDEN` must produce a pointer line in the rendered
   manifest. Catches "I added a category constant but didn't add it to
   the renderer."
3. **`test_workflow_contract_present_in_every_manifest`** — the three
   invariant text blocks (protocol + contract + policy) must appear in
   every tier's manifest. Catches "someone edited the template and
   accidentally dropped the hard policy."

If any of these fail, CI blocks merge. The design self-enforces.

---

## The ownership rule (in depth)

This is the single most important sentence in the workflow contract.
Two parties write files in a dotagent project:

```
┌──────────────────────────────────────────────────────────────┐
│  dotagent writes                          Claude writes      │
│  ───────────────                          ──────────────     │
│  CLAUDE.md (and sister adapters)          docs/bug-registry.md
│  SCOPE.md                                  docs/anti-patterns.md
│  CONTRACTS.md                              docs/redis-keys.md
│  contracts.md (root rollup)                docs/db-impact-map.md
│  git.md (from git.yaml)                    docs/dependency-map.md
│  Modules table inside project_brief.md     docs/architecture.md
│  PLAN.md (from module.yaml)                .agent/architecture.md
│  contract.frozen.md (post-freeze)          .agent/rules.md
│  .agent/.cache/sources.json                .agent/style.md (etc.)
│  .agent/.migration-log.md                  cycle's contract.md
│  .agent/.archive-log.md                    cycle's dev-handoff.md
│  .agent/memory/*/* (most)                  cycle's qa-findings.md
│                                            .agent/memory/personal/ (yours)
└──────────────────────────────────────────────────────────────┘
```

Two simple rules emerge:

1. If a file has a `<!-- generated by dotagent -->` banner, **dotagent
   owns it**. Hand-edits get wiped on the next sync.
2. If a file does not have that banner, **Claude (or you, the human)
   owns it**. dotagent will never touch it without explicit user action
   (e.g., `dotagent migrate` is opt-in and reversible).

The workflow contract calls this out explicitly because **the audit
findings showed that AI agents were skipping doc updates** — they
assumed dotagent regenerated everything, including `docs/bug-registry.md`.
It does not. Bug-registry is project truth, written by humans + AIs;
dotagent only indexes it.

---

## Token economics

CLAUDE.md before and after the redesign:

| Scenario | v1 (compendium) | v3 (manifest) |
|---|---|---|
| Single small project (<100 modules, ~20 bugs) | 5K tokens | 2K tokens |
| Mid project (~25 modules, ~150 bugs) | 30K tokens | 3K tokens |
| Aigent-size (25 modules, 380+ bugs, 22-section arch.md) | **~80K tokens** | **~3K tokens** |
| Big monorepo (>50 modules) | overflows 200K context | **stays ~5K tokens** |

The reduction is 90–97% on large projects. For Aigent specifically, the
saved tokens (~75K) are usable by Claude for *actual reasoning about
the task*, instead of being consumed by inert background context.

**Trade-off**: the AI now has to issue file-read tool calls to chase
pointers. That costs some round-trip latency (~50–200ms per file). But
each file is read once, only if needed, and is a fraction of the prior
embedded payload.

**Empirical**: in our internal tests, Claude follows the manifest's
"read these first" instructions ~95% of the time, then proceeds to do
2–5 targeted reads of source files based on the task. Net token cost
for a representative task: ~20K (3K manifest + 17K targeted reads) vs
v1's 80K (everything always loaded).

---

## The tier model

dotagent recognizes three project tiers, each producing a slightly
different CLAUDE.md:

| Tier | When | What changes |
|---|---|---|
| **project-root** | layered multi-service project (e.g. Aigent meta repo) | manifest includes cross-repo navigation, plan-negotiation, project-wide modules |
| **service-repo** | a service inside a layered project | manifest scopes to service-local docs; references parent via `parent:` field |
| **single-repo** | standalone project (legacy default) | manifest is flat — no inheritance, no cross-repo concerns |

Each tier has its own list of `SchemaEntry` rows. The renderer reads
the correct list based on filesystem signals (`.agent/git.yaml` present
→ project-root; `parent:` in config → service-repo; else → single-repo).

The same workflow contract + hard policy + reading protocol appear in
all three tiers (invariant text).

---

## How CLAUDE.md fits the dev↔QA cycle

The workflow contract isn't a suggestion — it's the **operating
procedure** that dotagent's CLI enforces at specific points:

```
┌────────────────────────────────────────────────────────────┐
│  Cycle phase             dotagent gate                     │
│  ──────────────         ────────────────────────            │
│  Plan negotiation       plan write-draft / write-review    │
│                         (--actor + --rationale required)   │
│                                                            │
│  Plan freeze            plan freeze                        │
│                         (rejects unless converged or       │
│                          --force --rationale)              │
│                                                            │
│  Contract draft         contract init                      │
│                                                            │
│  Contract rounds        contract round --actor             │
│                         (alternates dev/qa for round bump) │
│                                                            │
│  Contract score         contract score                     │
│                         (S1–S11; refuses convergence       │
│                          below threshold)                  │
│                                                            │
│  Contract freeze        contract freeze                    │
│                         (rejects on non-convergence;       │
│                          rollback gate fires if migration  │
│                          trigger without rollback)         │
│                                                            │
│  Module work            (you code; CLAUDE.md says how)     │
│                                                            │
│  Dev handoff            project handoff <id>               │
│                         (writes dev-handoff.md stub)       │
│                                                            │
│  QA review              project qa-record --result         │
│                                           --rationale      │
│                         (rejects without rationale)        │
│                                                            │
│  Ship                   project resolve <id>               │
│                         (requires QA pass)                 │
└────────────────────────────────────────────────────────────┘
```

CLAUDE.md tells the AI **what step they're in, what to read next, and
which CLI command to invoke.** dotagent enforces correctness at each
gate.

---

## How to extend

### Adding a new doc to the canonical schema

```python
# In src/dotagent/canonical_structure.py, find the relevant tier's
# entries tuple (e.g. _PROJECT_ROOT_ENTRIES) and add:

SchemaEntry(
    path="docs/your-new-doc.md",
    required=False,
    kind=KIND_FILE,
    category=CAT_ARCHITECTURE,  # pick the right category
    when_to_read="What the AI should read this for. YOU update when X.",
),
```

That's it. Coverage tests pass; manifest auto-includes the new doc.

### Adding a new category

Rare but supported:

1. Add the constant to `canonical_structure.py`: `CAT_NEW_THING = "new-thing"`
2. Add to `ALL_CATEGORIES` tuple in the same file
3. Add the section header tuple to `_CATEGORY_RENDER_ORDER` in
   `src/dotagent/render/manifest.py`
4. Re-run coverage tests

### Adding a new invariant policy

Edit `src/dotagent/render/workflow.py`'s `HARD_POLICY` constant. Add
a bullet. The `test_hard_policy_ban_phrases_present` test will need a
new assertion to keep that policy from being silently removed.

### Customizing for your project

The workflow contract template has placeholders (`{meta_branch}`,
`{bug_prefix}`) filled at render time. To add a new placeholder:

1. Update `WORKFLOW_CONTRACT_TEMPLATE` in `workflow.py`
2. Add the substitution in `manifest.py::render_manifest()`
3. Update tests if needed

---

## Honest tradeoffs

### What's strong

- **Source of truth flow.** Every fact lives in one source file. The
  manifest points; never duplicates.
- **Schema-driven completeness.** Coverage tests catch any drift.
- **Token economics.** 97% reduction at Aigent's scale.
- **Tier-aware.** project-root, service-repo, single-repo each get
  the right manifest.
- **Workflow contract.** Explicit instructions for the AI, not
  buried in comments or external docs.

### What's weak (or behavioral)

- **Post-task doc updates** are behavioral. dotagent can't yet enforce
  "you touched X.py but didn't update bug-registry." We rely on the AI
  reading the checklist and remembering. Planned v0.6 feature: a
  post-commit hook that flags drift.
- **`dotagent sync` is not auto-run.** AI must remember to run it
  after editing docs. Could be enforced by a post-commit hook.
- **`--no-verify` is bypassable.** Hard policy says never use it, but
  git allows it. Server-side branch protection (via the GitHub Actions
  workflow scaffolded by `dotagent git scaffold-protection`) closes
  this for the meta repo; nothing closes it for service repos by
  design.
- **Personal preferences in CLAUDE.local.md** require the AI to read
  the sidecar. Not all AIs do this automatically; the reading protocol
  step 3 instructs them.

### What's intentionally out of scope

- **LLM-generated content.** dotagent never invokes an LLM. The AI
  generates docs; dotagent indexes and renders.
- **Multi-project orchestration in dotagent itself.** Coda (or whatever
  orchestrator the user picks) drives multi-project workflows. dotagent
  just provides the per-project structure.
- **Doc-content audit.** "Is the architecture doc *correct*?" is for
  the code-aware audit feature (v0.5.0+) — see `CODE_AUDIT_PLAN.md`.

---

## What's next (roadmap)

| PR | Description | Status |
|---|---|---|
| Foundation | schema enrichment + workflow blocks + renderer + coverage tests | ✅ shipped (#34) |
| Adapter wiring | replace v1 renderer with manifest as default | next |
| `CLAUDE.local.md` sidecar | split per-actor + ephemeral content into gitignored file | planned |
| `--task` modes | task-aware section prioritization (bug-fix, design, review, qa, onboard) | planned |
| Contradictions appendix | doc-vs-doc + brief-vs-doc drift detection | planned |
| Code-aware crosschecks | `dotagent code audit` for doc-vs-code drift | planned (separate plan) |
| Service-repo polish | scoped service CLAUDE.md template + tests | next after this PR |
| Post-task drift hook | hook that flags "you touched X but didn't update Y" | v0.6+ |

---

## File references

| Source | What it owns |
|---|---|
| `src/dotagent/canonical_structure.py` | Schema entries, categories, tier definitions |
| `src/dotagent/render/workflow.py` | Invariant text blocks (protocol + contract + policy) |
| `src/dotagent/render/manifest.py` | Renderer; walks schema; emits markdown |
| `src/dotagent/adapters/render.py` | Old v1 renderer (still default until wired) |
| `tests/render/test_manifest_coverage.py` | Three coverage guarantees |
| `tests/test_canonical_structure.py` | Schema-shape tests |
| `tests/test_structure_checker.py` | Filesystem-vs-schema audit |

---

## Glossary

- **Manifest** — CLAUDE.md as a navigation index. Points at source files;
  doesn't embed their content.
- **Compendium** — the v1 pattern. Embedded everything inline.
  Deprecated by v0.5.0.
- **Tier** — one of project-root / service-repo / single-repo. Detected
  from filesystem signals.
- **Category** — one of 23 buckets that group canonical-schema entries
  into manifest sections. Every entry must declare one.
- **Ownership rule** — the load-bearing principle: dotagent owns generated
  files; Claude owns content files. No ambiguity.
- **Invariant text** — the three blocks (protocol + contract + policy)
  that appear identically across all dotagent projects, with only
  per-project placeholders substituted.
- **Coverage gate** — a CI test that fails if a schema entry is added
  without a category, or rendered manifest is missing a non-hidden entry.

---

_End of design document. Questions or suggestions? Open an issue at
https://github.com/dilawarabbas1/dotagent/issues._
