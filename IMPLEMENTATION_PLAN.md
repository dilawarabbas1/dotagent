# Implementation Plan — Layered Project Architecture

_Drafted: 2026-05-20  ·  Target: `dotagent` v0.4 → v0.6_

This plan turns the architecture we designed in chat into a sequenced set of PRs. Each PR is independently shippable, has its own tests, and merges to main behind a feature flag where state migration is involved.

---

## Goals (what this work delivers)

1. **Three-tier contract discoverability** — every repo has a `CONTRACTS.md` dashboard; the Project Root has a cross-repo `contracts.md` rollup.
2. **Layered structure** — Project Root holds cross-cutting context (brief, plan, hard rules); each service repo inherits via `parent:` and adds its own.
3. **`project_brief.md`** — durable business intent with OBJ-IDs, FEAT-IDs, RULE-IDs that every plan and contract cite for traceability.
4. **Plan negotiation** — Planner-Claude ↔ Codex (QA) negotiate the plan before it freezes, mirroring the existing contract flow.
5. **Cross-service modules** — one logical feature can span multiple repos with linked module slices.
6. **Git layout config** — `git.yaml` defines where Project Root meta lives (dedicated repo, non-`main` branch) with enforced branch reservation.
7. **Coda integration surface** — clean data-layer primitives that an orchestrator (Coda) can drive.

## Out of scope for this plan

- Auto-discovery of brief content from existing codebases (LLM extraction beyond what `dotagent init` already does)
- Cross-repo episodic memory aggregation in the server (already partially supported)
- Migration tooling from single-repo dotagent to layered structure (will write a migrator if user demand emerges)
- VS Code extension UI changes

---

## Sequencing — 11 PRs across 6 phases

```
Phase 1 (foundation, independent)
  PR #9  · per-repo CONTRACTS.md
  PR #12 · project_brief.md scaffolding

Phase 2 (wiring, depends on #12)
  PR #13 · FEAT/OBJ/RULE ID wiring + traceability checker
  PR #14 · CLAUDE.md renders brief subset

Phase 3 (plan negotiation, depends on #13)
  PR #15 · plan negotiation primitives (draft/review/round/diff/converged/freeze)
  PR #16 · auto-generated Modules table inside project_brief.md

Phase 4 (layered foundation, independent)
  PR #10 · parent: field + repo manifest
  PR #11 · cross-repo contracts.md rollup (depends on #9 + #10)

Phase 5 (git layout, depends on #10)
  PR #18 · git.yaml + meta sync commands
  PR #19 · branch reservation enforcement

Phase 6 (Coda integration)
  PR #17 · Planner drafts contracts per cycle (depends on #13 + #15)
```

Dependency graph:

```
       #9 ─────┐
                ├──► #11
       #10 ────┤
                ├──► #18 ──► #19
       #12 ──► #13 ──┬──► #14
                     ├──► #15 ──► #16
                     └──► #17
```

---

## PR-by-PR scope

### PR #9 — Per-repo `CONTRACTS.md` (Tier 2)

**Goal:** auto-generated, module-grouped contracts dashboard at `.agent/project/CONTRACTS.md` in every repo.

**Files to create**
- `src/dotagent/project/contracts_index.py` — pure-function renderer over `Project` + modules
- `src/dotagent/commands/contracts_index_cmd.py` — exposes `dotagent project contracts` + `--rebuild`, `--open`, `--frozen`, `--module`, `--json`
- `tests/project/test_contracts_index.py` — 6 tests (empty, open-only, frozen-only, mixed, JSON shape, rebuild after manual drift)

**Files to modify**
- `src/dotagent/project/contract.py` — call `regenerate_contracts_index()` after `init_contract`, `advance_round`, `freeze_contract`
- `src/dotagent/project/operations.py` — call it after `add_module`
- `src/dotagent/cli.py` — register the new command
- `src/dotagent/paths.py` — add `contracts_index` property

**Tests**
- empty repo → file with `_No contracts yet._`
- one module with two cycles (one open, one frozen) → table with both rows
- rebuild overrides manual edits (drift recovery)
- `--json` shape stable
- regenerated automatically by every contract op (test by patching the write hook)

**Effort:** ~250 lines including tests
**Risk:** low — pure rendering over existing state
**Acceptance:** every test passes; CONTRACTS.md auto-regenerates without explicit user call

---

### PR #12 — `project_brief.md` scaffolding + commands

**Goal:** introduce the brief file, its data model, and the four commands to manage it.

**Files to create**
- `src/dotagent/project/brief.py` — dataclasses: `Brief`, `Objective`, `Feature`, `HardRule`, `Glossary`, `Integration`; parser + renderer
- `src/dotagent/project/brief_template.py` — the Jinja template (the full template we agreed on in chat)
- `src/dotagent/commands/brief_cmd.py` — `dotagent project brief init / upload / show / edit / check`
- `tests/project/test_brief_parse.py` — round-trip parse → write → re-parse stability
- `tests/project/test_brief_init.py` — interactive Q&A path (mocked questionary)
- `tests/project/test_brief_check.py` — coverage audit
- `tests/project/test_brief_upload.py` — markdown upload (no LLM in v1)

**Files to modify**
- `src/dotagent/paths.py` — add `project_brief` property at `.agent/project_brief.md`
- `src/dotagent/cli.py` — register `brief` subgroup under `project`

**Behavior**
- `brief init` — interactive Q&A walks vision → personas → OBJs → FEATs → hard rules → constraints → glossary → tenancy → integrations → workflow
- `brief upload <path>` — parses an existing `.md` file into structured brief (v1: markdown only; PDF/DOCX deferred)
- `brief show [--section <name>] [--format json|md]` — read-only view
- `brief edit` — opens `$EDITOR`
- `brief check` — audits brief health: missing IDs, sections, last-reviewed > 180 days

**Tests** (10 total)
- parse a complete brief → all fields populated
- parse missing sections → fail with clear errors
- write → read round-trip is byte-equal
- `init` writes file with all required anchors
- `check` flags stale brief (>180 days)
- `check` flags duplicate OBJ-IDs
- `check` flags FEAT without OBJ reference
- `check` exits 0 on clean brief
- `--json` output schema is stable
- `upload` is idempotent

**Effort:** ~600 lines including tests
**Risk:** medium — large data model; template surface area
**Acceptance:** can author a brief end-to-end via `brief init` or by hand-editing the template

---

### PR #13 — FEAT/OBJ/RULE ID wiring + traceability checker

**Goal:** plan and contracts cite brief IDs; `dotagent project brief check` audits the chain.

**Files to create**
- `src/dotagent/project/traceability.py` — pure functions: `audit_obj_to_feat`, `audit_feat_to_module`, `audit_module_to_contract`, `audit_brief_version_drift`
- `tests/project/test_traceability.py` — 12 tests covering each audit path with positive + negative fixtures

**Files to modify**
- `src/dotagent/project/model.py` — add `brief_version`, `brief_objectives_covered`, `brief_features_covered`, `features_to_modules`, `modules_to_features` to `Project`; add `implements_features` to `Module`
- `src/dotagent/project/contract.py` — add `<!-- anchor: business-traceability -->` section to template; validate refuses if no FEAT-ID cited; add S11 rubric signal
- `src/dotagent/project/_signals.py` — implement S11 (business-traceability)
- `src/dotagent/project/contract_rubric.py` — bump max to 33; add band thresholds
- `src/dotagent/commands/brief_cmd.py` — implement `brief check` against the new audit functions

**Audit output shape**
```
Brief → Plan
  ✓ OBJ-01 → FEAT-02, FEAT-03 → modules exist
  ! OBJ-04 → FEAT-04 → no module implements FEAT-04 (orphan)

Features → Modules
  ✓ FEAT-01 → M01 (shipped)
  ! FEAT-04 → no module yet (gap)

Modules → Contracts
  ✓ M02 / cycle 01 cites FEAT-02, OBJ-01, OBJ-02
  ! M03 / cycle 01 cites no FEAT — missing business-traceability

Brief version drift
  ! M01 last contract cited brief_version: 2; current is 3
```

**Tests** (12)
- audit catches OBJ → FEAT orphan
- audit catches FEAT → Module gap
- audit catches Module → Contract missing FEAT citation
- audit catches version drift
- audit returns clean report when chain is intact
- S11 scores 0 on missing FEAT citation
- S11 scores 3 on FEAT + OBJ both cited
- contract validate fails when business-traceability section is empty
- contract validate passes when FEAT-ID is cited
- model serialization preserves new fields
- `brief check` exits non-zero on any audit failure
- `brief check --json` shape stable

**Effort:** ~500 lines including tests
**Risk:** medium — touches the contract validate + rubric; needs careful regression testing
**Acceptance:** existing 230 tests still green; new tests added; `brief check` produces the report shape above

---

### PR #14 — CLAUDE.md renders brief subset

**Goal:** each repo's CLAUDE.md includes the structured subset of the brief (OBJs, FEATs, Hard Rules, Glossary, Tenancy, Non-goals), filtered for that repo.

**Files to modify**
- `src/dotagent/adapters/render.py` — new `_render_brief_excerpt()` function; new section `## Project context`
- `src/dotagent/context.py` — `build()` loads brief.yaml if present, passes structured excerpt
- `src/dotagent/sources.py` — index `project_brief.md` if present at `.agent/project_brief.md`
- `tests/test_adapters.py` — add tests that brief OBJ/FEAT/RULE flow into CLAUDE.md
- `tests/test_context.py` — assert excerpt is filtered per-repo (only this repo's modules appear)

**Selective embed rule (per-repo filtering)**
For a service repo, render only:
- All OBJ-IDs + titles (project-wide)
- FEATs this repo implements (filtered via `features_to_modules` + repo's `module_ids`)
- All hard RULE-IDs (project-wide)
- Glossary, Tenancy, Non-goals (project-wide)

**Tests** (6 added)
- CLAUDE.md includes "## Project context" section when brief is present
- CLAUDE.md does NOT include the section when no brief exists (backward compat)
- only this repo's FEATs appear (filter is correct)
- all hard rules appear (no filtering)
- brief_version stamped in section header
- order of subsections is stable

**Effort:** ~200 lines including tests
**Risk:** low — additive change to existing render path
**Acceptance:** sister-services awareness ships; backward compat preserved (repos without a brief render unchanged)

---

### PR #15 — Plan negotiation primitives

**Goal:** introduce the dev↔QA negotiation pattern for `plan.yaml` itself. Mirrors the existing contract flow.

**Files to create**
- `src/dotagent/project/plan_negotiation.py` — `draft_plan`, `review_plan`, `advance_plan_round`, `diff_plan`, `freeze_plan` (mirrors contract.py)
- `src/dotagent/commands/plan_cmd.py` — `dotagent project plan draft / review / round / diff / converged / freeze / show`
- `tests/project/test_plan_negotiation.py` — 12 tests parallel to existing contract round/freeze tests

**Files to modify**
- `src/dotagent/paths.py` — add `plan_negotiations_dir`, `plan_draft_path`, `plan_frozen_path`, `plan_round_dir`
- `src/dotagent/project/model.py` — add `Plan` dataclass (separate from current `Project`; `plan.yaml` becomes more structured)
- `src/dotagent/cli.py` — register `plan` subgroup under `project`

**File layout (added)**
```
.agent/project/
├── plan.yaml                       (in-effect plan; was here before)
├── plan.frozen.yaml                (snapshot from last freeze)
└── plan-negotiations/
    └── 01/
        ├── plan.draft.yaml         (live working doc)
        ├── negotiation-log.md      (every round + rationale)
        └── rounds/
            ├── 01-planner.yaml
            ├── 02-qa.yaml
            ├── 03-planner.yaml
            └── 04-qa.yaml
```

**Behavior**
- `plan draft --actor planner --from-stdin` — writes `plan.draft.yaml` + records round
- `plan review --actor qa --from-stdin --rationale "..."` — writes QA's counter + records round
- `plan converged` — exit 0 if last two rounds (different actors) hash-match, 1 otherwise
- `plan freeze` — converged → plan.yaml + plan.frozen.yaml; `--force` overrides

**Tests** (12)
- empty initial state → `plan draft` opens round 1
- two actors alternate writes correctly increments rounds
- same-actor re-write does NOT increment (refinement of same round)
- convergence detected when content hashes match
- diff shows changes between rounds
- freeze writes immutable snapshot
- freeze refuses on non-converged plan (without --force)
- `--force` records reason in log
- idempotent re-freeze is a no-op
- structured negotiation log parseable
- exits 0/1 correctly for `converged` command
- `--json` output shape

**Effort:** ~700 lines including tests
**Risk:** medium-high — new state machine; high test surface
**Acceptance:** plan can be drafted, reviewed, converged, frozen via 6 CLI calls without any LLM in the loop (orchestrator-friendly)

---

### PR #16 — Auto-generated Modules table inside `project_brief.md`

**Goal:** the Modules section of the brief becomes a generated dashboard that updates on every project event.

**Files to modify**
- `src/dotagent/project/brief.py` — add `regenerate_modules_section()` that reads `plan.yaml` + `module.yaml` files and rewrites the section between anchors
- `src/dotagent/project/operations.py` — call after `add_module`, `start_cycle`, etc.
- `src/dotagent/project/contract.py` — call after every contract operation
- `tests/project/test_brief_modules_section.py` — 4 tests

**Section anchors added**
```markdown
<!-- anchor: modules-table-begin -->
... generated content ...
<!-- anchor: modules-table-end -->
```

dotagent only ever rewrites between the anchors; hand-written content above/below is preserved.

**Tests** (4)
- empty plan → "no modules yet" placeholder
- add module → row appears in table
- ship module → state transitions to `shipped`
- hand-edits outside the anchors survive regeneration

**Effort:** ~150 lines including tests
**Risk:** low — bounded edits to a known section
**Acceptance:** brief reads top-to-bottom as a unified doc, but the volatile section stays current

---

### PR #10 — `parent:` field + repo manifest (layered foundation)

**Goal:** `.agent/config.yaml` accepts a `parent:` field; sync merges parent layer + service layer.

**Files to modify**
- `src/dotagent/config.py` — accept `parent:` field; resolve relative paths against `.agent/`
- `src/dotagent/context.py` — `build()` loads parent context first if `parent:` is set, overlays local
- `src/dotagent/sources.py` — index parent's `docs/` if present
- `src/dotagent/paths.py` — add `parent_agent_dir` resolver
- `tests/test_layered_context.py` — 8 tests

**Behavior**
- `.agent/config.yaml: { parent: "../.." }` → loads `../../.agent/` first, then local overrides
- Sections from parent's `.agent/*.md` flow into rendered CLAUDE.md under `## Project context`
- Service-level files (`rules.md`, `style.md`, etc.) overlay parent
- `docs/*.md` are concatenated (parent's first, then service's)
- Memory layers (`working/`, `episodic/`, `personal/`) are NOT inherited (service-local only)

**Tests** (8)
- no `parent:` field → identical behavior to today (backward compat)
- `parent: "../.."` → parent's `architecture.md` appears in CLAUDE.md
- service's `rules.md` overrides parent's same section
- both `docs/` directories indexed (counts aggregate)
- parent's hard rules included; service's added
- cycle-detection: A → B → A errors out
- missing parent path errors with clear message
- absolute parent path supported

**Effort:** ~400 lines including tests
**Risk:** medium-high — touches the central context-build path
**Acceptance:** running `dotagent sync` in a service repo merges Project Root + local; existing single-repo setups unchanged

---

### PR #11 — Cross-repo `contracts.md` rollup (Tier 1)

**Goal:** Project Root has a single `contracts.md` aggregating contract state across all child repos.

**Files to create**
- `src/dotagent/project/contracts_rollup.py` — walks `repos[]` from plan.yaml, reads each repo's `.agent/project/CONTRACTS.md` data (or recomputes), renders rollup
- `tests/project/test_contracts_rollup.py` — 5 tests

**Files to modify**
- `src/dotagent/commands/contracts_index_cmd.py` — add `--all-repos` flag
- `src/dotagent/project/operations.py` — regenerate rollup when called from Project Root

**Tests** (5)
- 3 repos with mixed open/frozen → table with all rows correctly grouped
- one repo missing CONTRACTS.md → rebuilt on the fly
- cross-service modules section appears
- `--json` shape stable
- absent `repos[]` → command errors clearly

**Effort:** ~250 lines including tests
**Risk:** medium — depends on filesystem layout matching the manifest
**Acceptance:** at Project Root, `dotagent project contracts --all-repos` produces the full cross-repo dashboard

---

### PR #18 — `git.yaml` + meta sync commands

**Goal:** Project Root knows where it lives in git; meta content syncs via `dotagent git push / pull / status`.

**Files to create**
- `src/dotagent/git_layout.py` — `GitLayout` dataclass; YAML parser; branch-rules schema
- `src/dotagent/commands/git_cmd.py` — `dotagent git status / push / pull / rebuild / init / clone-services`
- `tests/test_git_layout.py` — 10 tests

**Files to modify**
- `src/dotagent/paths.py` — add `git_yaml`, `git_md`
- `src/dotagent/cli.py` — register `git` subgroup

**`git.yaml` schema (locked from chat)**
```yaml
meta:
  strategy: dedicated_repo
  remote: git@github.com:...
  branch: dotagent/meta            # never main
  main_branch_policy: locked
repos:
  - id: backend
    path: ./backend
    remote: git@github.com:...
    default_branch: main
branch_rules:
  - remote: git@github.com:...
    branches:
      main: { allowed_paths: [], forbidden_paths: ["**/*"], description: "..." }
      dotagent/meta: { allowed_paths: [...], forbidden_paths: [...], description: "..." }
```

**Behavior**
- `git status` — show drift between local and meta remote
- `git push` — commit + push meta-only files to the meta branch; refuses if pushing code
- `git pull` — fetch + fast-forward
- `git rebuild` — regenerate `git.md` from `git.yaml`
- `git init` — interactive wizard to create `git.yaml`
- `clone-services` — reads `repos[]`, runs `git clone` for each as a sibling

**Tests** (10)
- parse minimal `git.yaml`
- parse full `git.yaml` with all options
- reject `branch: main` for meta (lint rule)
- `status` shows clean / dirty / behind
- `push` includes only meta files
- `push` refuses on code file presence
- `pull` fast-forwards cleanly
- `pull` aborts on merge conflict
- `rebuild` produces stable output
- `clone-services` clones each repo as sibling

**Effort:** ~500 lines including tests
**Risk:** medium — git subprocess invocations; merge-conflict edge cases
**Acceptance:** Project Root can be initialized + pushed + cloned via the new commands

---

### PR #19 — Branch reservation enforcement

**Goal:** locally and on GitHub, prevent the meta branch from accepting code and main from being written.

**Files to create**
- `src/dotagent/scaffolds/branch_rules.yml.j2` — GitHub Actions workflow template
- `src/dotagent/scaffolds/pre-push-meta.sh` — local pre-push hook template
- `src/dotagent/commands/git_cmd.py` (additions) — `git init-hooks`, `git scaffold-protection`, `git verify`
- `tests/test_branch_rules.py` — 8 tests

**Behavior**
- `dotagent git init-hooks` — installs `.git/hooks/pre-push` that runs `dotagent git verify --target <remote>::<branch>`
- `dotagent git verify --branch <name>` — checks staged/pushed files against `branch_rules`; exits non-zero on violation
- `dotagent git scaffold-protection` — writes `.github/workflows/branch-rules.yml` + prints GitHub UI instructions for branch protection

**Tests** (8)
- verify passes on clean meta push
- verify fails on Python file in meta push
- verify fails on Dockerfile in meta push
- verify against locked main rejects everything
- pre-push hook installs idempotently
- scaffold writes Action that actually runs `dotagent git verify`
- multiple branch rules apply correctly
- exit codes consistent

**Effort:** ~350 lines including tests
**Risk:** medium — git hook installation is platform-sensitive
**Acceptance:** pushing `auth.py` to `dotagent/meta` is rejected locally AND fails CI on the meta repo

---

### PR #17 — Planner drafts contracts per cycle (Coda integration)

**Goal:** `dotagent project contract init` accepts a `--from-brief` mode that pre-populates the business-traceability section from the brief + plan, so Planner-Claude (via Coda) starts with FEAT-IDs cited.

**Files to modify**
- `src/dotagent/project/contract.py` — `init_contract()` accepts `from_brief: bool = False`; renders business-traceability with brief lookup
- `src/dotagent/commands/contract_cmd.py` — add `--from-brief` flag
- `tests/project/test_contract_init_from_brief.py` — 4 tests

**Behavior**
- With `--from-brief`: contract.md's business-traceability section is pre-populated:
  ```
  ## Business traceability
  Feature: FEAT-02 (password recovery)
  Objectives: OBJ-01, OBJ-02
  Behaviors this slice must satisfy:
  - "new password in effect immediately"
  - ...
  ```
- Without the flag: same blank template as today (backward compat)

**Tests** (4)
- `--from-brief` populates business-traceability when module.implements_features = [FEAT-02]
- module not mapped to any FEAT → error with clear message
- absent brief → error with clear message
- without the flag → template identical to today

**Effort:** ~200 lines including tests
**Risk:** low — additive to existing init path
**Acceptance:** Coda can call `dotagent project contract init --module M02 --from-brief` and get a contract with traceability pre-filled

---

## Cross-cutting concerns

### Backward compatibility
- Every PR must leave single-repo dotagent users unaffected (no `parent:`, no brief, no rollup → same behavior as today).
- The 230 existing tests must remain green throughout. Any test that breaks needs an explicit justification in the PR.

### Hooks regeneration
- `dotagent sync` must regenerate ALL generated files (CONTRACTS.md, contracts.md, SCOPE.md, brief modules table, CLAUDE.md, git.md). One traversal, one regeneration call.
- Each PR that adds a new generated file extends the sync regeneration list.

### Banner convention
Every generated file starts with:
```
<!-- GENERATED by dotagent — do not edit. Run `<command>` to refresh. -->
<!-- Last regenerated: <ISO timestamp> -->
```

### Tests location convention
- Per-feature: `tests/project/test_<feature>.py`
- Cross-cutting: `tests/test_<aspect>.py`
- Each PR adds tests in the matching location

### CLI surface conventions
- All new subcommands under `dotagent project <subgroup>` for project-level commands; under `dotagent git` for git-layout commands
- Every command supports `--json` where output makes sense to machine-parse
- Every state-changing command supports `--dry-run`

---

## Risks + mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Layered context (#10) introduces sync cycles | medium | high | cycle-detection lint in PR #10's tests |
| Plan negotiation log gets large for slow-converging plans | low | low | rotation strategy in PR #15 (compress rounds after freeze) |
| GitHub Action enforcement (#19) requires admin perms to install | high | low | docs explicitly call this out; provide manual steps |
| Brief upload (#12) gets future requests for PDF/DOCX | high | low | defer to v2; markdown-only in v1 |
| `parent:` field becomes a recursion footgun | low | medium | cap depth at 3 levels; error on cycles |
| Cross-service modules drift between repos | medium | medium | `dotagent project brief check` audits cross_module references |

---

## Release plan

- **v0.4** — PRs #9, #12, #13, #14 (per-repo CONTRACTS, brief, traceability, CLAUDE rendering)
- **v0.5** — PRs #15, #16, #17 (plan negotiation, brief modules section, Planner integration)
- **v0.6** — PRs #10, #11, #18, #19 (layered foundation, cross-repo rollup, git layout, enforcement)

Versions bumped in `pyproject.toml` + tagged at the end of each phase.

---

## What we're NOT touching (preserve these as-is)

- Memory layer: working / episodic / semantic / personal — no shape changes
- Auto-Dream pipeline — no shape changes
- Adapter file naming (CLAUDE.md, .cursorrules, etc.) — no changes
- Identity / config / paths overall structure — only additions
- Existing 230 tests — all must remain green

---

## Decision log (from chat)

- Brief lives at `Project Root/.agent/project_brief.md` (not at repo root)
- Brief contains **Features** with business outcomes (no module IDs, no tech terms)
- IDs format: `OBJ-NN`, `FEAT-NN`, `RULE-NN`, `M-NN`, `SC-NN`
- Three-tier contract discoverability: Project Root `contracts.md` → repo `CONTRACTS.md` → cycle dirs
- Meta repo strategy: dedicated repo (`aigent-meta` pattern); meta on `dotagent/meta` branch; `main` locked
- Plan negotiation: Planner-Claude ↔ Codex (QA), orchestrated by Coda; dotagent provides primitives only
- Generated files have banner + `--rebuild` recovery; hand-edits are wiped on sync
- File casing: `CONTRACTS.md` (caps) for per-repo; `contracts.md` (lowercase) at Project Root for the rollup — match each tier's convention

---

## Approval needed before starting

1. **PR order** — start with PR #9 (smallest, fastest win) or PR #12 (foundational for everything brief-related)?
2. **Version cadence** — ship per-PR (release v0.4.1, v0.4.2, ...) or batch per phase (release v0.4 once all of phase 1 lands)?
3. **Hold-back PRs** — anything in the list above to defer past v0.6?
