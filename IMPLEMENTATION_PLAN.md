# Implementation Plan — Layered Project Architecture (v2)

_Drafted: 2026-05-20  ·  Target: `dotagent` v0.4 → v0.7  ·  Estimated calendar: 6–8 weeks_

---

## Executive summary

This plan extends `dotagent` from a single-repo tool into a **layered project architecture** that supports multi-service projects, durable business-intent capture, plan/contract negotiation primitives, document lifecycle management, and clean separation between dotagent (data layer) and any orchestrator (Coda, scripts, humans) that drives it.

The work spans **14 PRs across 7 phases**. Phases 0–1 are blocking (they define the canonical schema and migration story everything else depends on). The rest are independently shippable with clear dependency edges.

**Key shifts from the v1 plan:**

1. **dotagent is decoupled from Coda.** dotagent provides files + CLI primitives. It does not invoke LLMs, does not know about Planner/QA roles internally, does not orchestrate. Coda (or any other tool) reads the generated files and calls dotagent's primitives.
2. **Canonical structure is now a first-class concept** with a schema, a doctor checker, and a migrator. Without this, the layered structure breaks every existing single-repo installation.
3. **Three install modes are explicitly handled** (fresh / mid-project / pre-v0.4 upgrade) by a single `dotagent migrate` command that detects mode and routes.
4. **Document lifecycle is in scope.** Bug registry, anti-patterns, shipped modules, frozen contracts — all have explicit archive triggers and reversal.
5. **Bug registry is tiered** (Project Root + per-service) with prefix conventions and cross-references.
6. **Main is locked ONLY in the meta repo.** Service repos' `main` branches are normal code branches.

---

## Problem statement (why this work matters)

Today's `dotagent` (v0.3) is excellent for **one repo, one developer, one AI tool**. It breaks down in three places:

1. **Multi-service projects** have no first-class concept. A user with 3 service repos copies-pastes `.agent/` content between them or accepts drift. There's no place for project-wide hard rules, no cross-service contract dashboard, no shared brief.
2. **Business intent is implicit.** The brief, OBJs, and FEATs live in someone's head (or a Notion doc). Contracts are written with no anchor to the business "why." There's no traceability from a shipped commit back to a business objective.
3. **Documents grow forever.** Bug registries accumulate fixed bugs. Anti-patterns accumulate rescinded ones. There's no policy or tooling to age content out.

These three together mean dotagent struggles past month 3 of any non-trivial project. This plan fixes all three.

---

## Locked design decisions (from chat)

These are **closed**. Re-opening any of them invalidates dependent PRs.

| # | Decision | Notes |
|---|---|---|
| D1 | dotagent is a data layer. No LLM invocation inside dotagent. | Orchestrators (Coda, scripts) read files and call CLI primitives. |
| D2 | Brief lives at `Project Root/.agent/project_brief.md` (template locked, full version captured in this plan). | Hand-written or AI-drafted on init; rarely changes. |
| D3 | ID conventions: `OBJ-NN`, `FEAT-NN`, `RULE-NN`, `M-NN`, `SC-NN`, `<PREFIX>-NNNN` for bugs. | `bug_id_prefix:` declared in each repo's `.agent/config.yaml`. |
| D4 | Three-tier contract discoverability: `Project Root/contracts.md` → `<repo>/.agent/project/CONTRACTS.md` → cycle dir. | Top tier and middle tier are auto-generated. |
| D5 | Meta repo strategy: dedicated repo (e.g., `aigent-meta`). | Service repos remain independent. |
| D6 | Meta lives on `dotagent/meta` branch (never `main`). | Meta repo's `main` is locked. **Service repos' `main` is NOT locked.** |
| D7 | Plan negotiation primitives mirror contract negotiation (rounds, hash-convergence, freeze). | dotagent stores and validates; does not draft. |
| D8 | Generated files carry a banner + `--rebuild` recovery. Hand-edits to generated files are wiped on sync. | Convention enforced by docstring + visible banner at top of every generated file. |
| D9 | File casing: `CONTRACTS.md` (caps) per-repo; `contracts.md` (lowercase) at Project Root for the cross-repo rollup. | Matches each tier's level of authority. |
| D10 | Schema version stamped at `.agent/.version`. Doctor + migrate read this. | Single source of truth for "what shape should this be." |

---

## Goals

1. Three-tier contract discoverability — every repo has a `CONTRACTS.md` dashboard; Project Root has a cross-repo `contracts.md` rollup.
2. Layered structure — Project Root holds cross-cutting context (brief, plan, hard rules); each service repo inherits via `parent:` and adds its own.
3. `project_brief.md` — durable business intent with OBJ/FEAT/RULE IDs that every plan and contract cite.
4. Plan negotiation primitives — pure data ops (write, read, diff, converged, freeze); no LLM invocation.
5. Cross-service modules — one logical feature can span multiple repos with linked module slices.
6. Git layout config (`git.yaml`) — defines where Project Root meta lives, with enforced branch reservation in the meta repo (not service repos).
7. **Canonical structure schema + doctor + migrator** — defines what a dotagent project should look like and helps existing installs upgrade.
8. **Document lifecycle / archive policy** — explicit triggers and tooling so docs don't grow forever.
9. **Tiered bug registry** — project-root master + per-repo, with prefix conventions and cross-references.

## Non-goals (deferred or out of scope)

- LLM-based brief extraction from PDF/DOCX (v1 supports markdown only; PDF/DOCX deferred to a post-v0.7 PR if demand emerges).
- Auto-merge of bug-registry entries across services (humans tag the right level).
- VS Code extension UI changes (separate effort).
- Cross-org access controls in the server (already partially supported; not in scope here).
- Replacement of the four memory layers (working / episodic / semantic / personal) — additive only.

---

## Affected install modes and how each is handled

| Mode | Detection signal | Command flow | What happens |
|---|---|---|---|
| **1 · Fresh install at project start** | no `.git/`, no `.agent/`, empty dir | `dotagent init` | Writes canonical structure for the chosen tier (project-root or service), populates brief stub, plan stub, git.yaml stub. |
| **2 · Mid-project install, no prior dotagent** | `.git/` exists, no `.agent/`, has code/docs | `dotagent init` | Runs discovery (READMEs, package.json, etc.), drafts brief stub from discovered context, ingests `docs/*.md` if present, writes canonical structure. |
| **3 · Existing dotagent install, pre-v0.4 schema** | `.agent/` exists, `.agent/.version` < 0.4 (or missing) | `dotagent migrate` | Compares against canonical schema, prints preview, on confirm: moves files into v0.4 layout, creates missing files (brief stub), preserves all content, logs every move to `.agent/.migration-log.md` for rollback. |

`dotagent doctor` recognizes each mode and prints the right next-step command at the top of its output. No silent surprises.

---

## Document lifecycle (archive policy)

`docs/` becomes layered. Active content stays in `docs/*.md`. Historical content moves to `docs/archive/YYYY/*.md`. Specific rules per source:

| Source | Active in | Archive trigger | Goes to | Surfaced in CLAUDE.md |
|---|---|---|---|---|
| `docs/bug-registry.md` (OPEN entries) | `docs/bug-registry.md` | `status: fixed` AND fix frozen ≥30 days | `docs/archive/<YYYY>/bug-registry.md` | counts only ("142 historical bugs") |
| `docs/anti-patterns.md` | `docs/anti-patterns.md` | `rescinded: true` + rationale | `docs/archive/<YYYY>/anti-patterns.md` | rescinded-but-recent (90d) shown |
| `docs/dependency-map.md` | `docs/dependency-map.md` | service/component removed | `docs/archive/<YYYY>/deprecated-dependencies.md` | linked from main map |
| Module dirs (shipped) | `.agent/project/modules/<id>/` | state=`shipped` AND last cycle frozen ≥90 days | `.agent/project/archive/<YYYY>/<id>/` | summary line in modules table |
| Semantic rules (already handled) | `.agent/memory/semantic/.../rule.md` | existing lifecycle: review_after expired + grace period | `.agent/memory/semantic/expired/...` | excluded from active rules |
| Frozen contracts | move with the module | (follows module archive) | follows module | not directly |

All archives are reversible via `dotagent archive restore <entry-id>`. Every move is logged.

---

## Tiered bug registry — explicit rule

```
Project Root/docs/bug-registry.md          ← CROSS-SERVICE bugs (AGT-####)
backend/docs/bug-registry.md               ← backend-only bugs (BE-####)
customer-portal/docs/bug-registry.md       ← portal-only bugs (PORTAL-####)
admin-portal/docs/bug-registry.md          ← admin-only bugs (ADMIN-####)
```

**Prefix declared in config.** Each `.agent/config.yaml` has a `bug_id_prefix:` field. `dotagent doctor` warns on prefix collisions.

**Cross-references** are first-class. A cross-service bug at Project Root (`AGT-0042`) that surfaces in backend gets a stub entry in backend's registry pointing up: "see Project Root AGT-0042 — this is where it manifests in this repo."

**CLAUDE.md** per-repo includes: top 20 by severity of this repo's own bugs PLUS a summary of cross-service bugs that touch this repo.

---

## The full PR plan — 14 PRs across 7 phases

Phase 0 and Phase 1 are **blocking** — every subsequent PR depends on the canonical schema being in place.

```
Phase 0 — Foundation: schema + migration (BLOCKING)
  PR #1 · Canonical structure schema + doctor checks
  PR #2 · dotagent migrate (handles modes 1, 2, 3)

Phase 1 — Document lifecycle (independent of Phase 0 schema location, but should land same release)
  PR #3 · Archive command family + automatic triggers
  PR #4 · Bug registry tiering + prefix declaration

Phase 2 — Brief + traceability
  PR #5 · project_brief.md scaffolding + commands (init/upload/show/edit)
  PR #6 · FEAT/OBJ/RULE wiring + traceability checker + S11 rubric signal
  PR #7 · CLAUDE.md renders brief subset (per-repo filtered)

Phase 3 — Contract discoverability
  PR #8 · Per-repo CONTRACTS.md (Tier 2 dashboard)

Phase 4 — Plan negotiation
  PR #9  · Plan negotiation primitives (write-draft / write-review / converged / freeze)
  PR #10 · Auto-generated Modules table inside project_brief.md

Phase 5 — Layered structure
  PR #11 · parent: field + repo manifest
  PR #12 · Cross-repo contracts.md rollup (Tier 1)

Phase 6 — Git layout
  PR #13 · git.yaml + meta sync commands (push/pull/status/clone-services)
  PR #14 · Branch reservation enforcement (meta repo only)
```

### Dependency graph

```
PR #1 (schema) ──┬──► PR #2 (migrate)
                  └──► every later PR

PR #3 (archive) ──┐
                   ├── independent of each other; both depend on #1
PR #4 (bug tier) ──┘

PR #5 (brief)  ──► PR #6 (wiring)  ──┬──► PR #7  (CLAUDE renders)
                                       ├──► PR #9  (plan negotiation)
                                       └──► PR #10 (modules table)

PR #8 (CONTRACTS.md) ───────────────────► PR #12 (cross-repo rollup)

PR #11 (parent:) ──────────────────────► PR #12 (cross-repo needs parent)
                                       └► PR #13 (git layout needs manifest)

PR #13 (git.yaml) ──► PR #14 (enforcement)
```

---

## PR-by-PR full specification

### PR #1 — Canonical structure schema + doctor checks

**Goal:** define, in code, what a v0.4+ dotagent project should look like. Make `doctor` aware of every deviation.

**Why it's first:** every later PR needs to know "where does this file go?" and "is this layout valid?" Without a canonical schema, every PR re-invents structural assumptions.

**Files to create**

| Path | Purpose |
|---|---|
| `src/dotagent/canonical_structure.py` | Declarative schema: list of `(path, required, type, tier, description)` tuples |
| `src/dotagent/structure_checker.py` | Compares filesystem against schema; returns list of deviations |
| `src/dotagent/commands/structure_cmd.py` | `dotagent structure show / check / show --tier project-root` |
| `tests/test_canonical_structure.py` | 8 tests |
| `tests/test_structure_checker.py` | 10 tests |

**Files to modify**

| Path | Change |
|---|---|
| `src/dotagent/doctor.py` | Add `_check_canonical_structure()` that runs `structure_checker.check()` |
| `src/dotagent/commands/doctor_cmd.py` | Surface structure deviations with their fix suggestions |
| `src/dotagent/paths.py` | Add `version_file` property → `.agent/.version` |
| `src/dotagent/cli.py` | Register `structure` subgroup |

**Schema entries (key ones)**

```python
TIER_PROJECT_ROOT = [
    SchemaEntry(".agent/.version",                     required=True,  kind="file"),
    SchemaEntry(".agent/config.yaml",                  required=True,  kind="file"),
    SchemaEntry(".agent/architecture.md",              required=True,  kind="file"),
    SchemaEntry(".agent/rules.md",                     required=True,  kind="file"),
    SchemaEntry(".agent/project_brief.md",             required=True,  kind="file"),
    SchemaEntry(".agent/git.yaml",                     required=False, kind="file"),
    SchemaEntry(".agent/git.md",                       required=False, kind="generated"),
    SchemaEntry(".agent/project/plan.yaml",            required=True,  kind="file"),
    SchemaEntry(".agent/project/SCOPE.md",             required=False, kind="generated"),
    SchemaEntry(".agent/project/CONTRACTS.md",         required=False, kind="generated"),
    SchemaEntry(".agent/project/modules/",             required=False, kind="dir"),
    SchemaEntry("docs/bug-registry.md",                required=False, kind="file"),
    SchemaEntry("docs/architecture.md",                required=False, kind="file"),
    SchemaEntry("docs/service-registry.md",            required=False, kind="file"),
    SchemaEntry("contracts.md",                        required=False, kind="generated"),
    SchemaEntry("CLAUDE.md",                           required=False, kind="generated"),
]

TIER_SERVICE_REPO = [
    SchemaEntry(".agent/.version",                     required=True,  kind="file"),
    SchemaEntry(".agent/config.yaml",                  required=True,  kind="file"),
    SchemaEntry(".agent/architecture.md",              required=True,  kind="file"),
    SchemaEntry(".agent/rules.md",                     required=True,  kind="file"),
    SchemaEntry(".agent/project/plan.yaml",            required=True,  kind="file"),
    SchemaEntry(".agent/project/CONTRACTS.md",         required=False, kind="generated"),
    SchemaEntry("docs/bug-registry.md",                required=False, kind="file"),
    SchemaEntry("CLAUDE.md",                           required=False, kind="generated"),
    # ... rest
]
```

**Schema versioning rules**

- `.agent/.version` is a single line: a semver string matching the dotagent release that wrote the structure.
- On every release that bumps schema (PR #1 → `0.4.0`, future PRs that touch schema → next minor), this is updated.
- `dotagent doctor` reads it; if it doesn't match `dotagent --version`, prints "run `dotagent migrate` first."

**Tests** (18 total)

- Schema parses without error
- `structure_check()` returns empty on a clean v0.4 install
- Missing required file → deviation flagged
- Generated file present without banner → warning, not error
- Tier detection: `.agent/git.yaml` present → tier = project-root
- Tier detection: `.agent/config.yaml` has `parent:` → tier = service
- Tier ambiguous → user picks via `--tier` flag
- Schema version mismatch → flagged
- `dotagent structure show` produces stable output
- `dotagent structure check --tier service-repo` runs on a fixture
- Multiple deviations reported together (not just first)
- `--json` shape stable
- Hidden files (e.g., `.imported/`) excluded from deviation scan
- "Unexpected file" warnings are non-fatal
- Custom user files in `.agent/` flagged as info, not error
- doctor exit code: 0 on clean, 1 on any deviation
- Schema fixtures cover both tiers
- Bare `dotagent structure show` requires no project

**Effort:** ~600 lines including tests
**Risk:** medium — central to everything downstream
**Acceptance:** `dotagent doctor` on a v0.3 install identifies it as pre-v0.4 and recommends `dotagent migrate`

---

### PR #2 — `dotagent migrate` (three-mode install handling)

**Goal:** the upgrade path. Detects which install mode the user is in and routes.

**Why second:** without this, every existing dotagent user is stuck on v0.3 when v0.4 ships.

**Files to create**

| Path | Purpose |
|---|---|
| `src/dotagent/migration/__init__.py` | Migration runner; loads version-pair handlers |
| `src/dotagent/migration/detector.py` | Detects mode 1/2/3 |
| `src/dotagent/migration/v0_3_to_v0_4.py` | The actual migration logic for this version pair |
| `src/dotagent/migration/log.py` | `.agent/.migration-log.md` writer; rollback reader |
| `src/dotagent/commands/migrate_cmd.py` | `dotagent migrate [--plan] [--to <ver>] [--rollback]` |
| `tests/test_migration_detector.py` | 6 tests |
| `tests/test_migration_v0_3_to_v0_4.py` | 12 tests (per-rule coverage) |
| `tests/test_migration_rollback.py` | 4 tests |

**Files to modify**

| Path | Change |
|---|---|
| `src/dotagent/cli.py` | Replace existing `migrate-cco` registration with broader `migrate` group; keep `migrate-cco` as alias |

**Migration rules from v0.3 to v0.4**

| Source path | Target path | Notes |
|---|---|---|
| (no `.agent/.version`) | `.agent/.version` = `0.4.0` | Always write |
| (no `project_brief.md`) | `.agent/project_brief.md` (stub template) | Stub only; user fills |
| `.agent/project/plan.yaml` (existing fields) | (preserved; new fields added with empty defaults) | brief_version=0, brief_objectives_covered=[], etc. |
| (existing `docs/bug-registry.md` with mixed-status entries) | Active stays; fixed entries archived to `docs/archive/<YYYY>/bug-registry.md` | Only if `dotagent archive run` confirms (separate step) |
| (no `bug_id_prefix:` in config) | Inferred from first bug-registry entry's prefix, or asked interactively | Logged in migration log |

**Modes detected**

```python
def detect_mode(repo_root: Path) -> Mode:
    has_git = (repo_root / ".git").exists()
    has_agent = (repo_root / ".agent").is_dir()
    has_version = (repo_root / ".agent" / ".version").exists()

    if not has_agent and not has_git:
        return Mode.FRESH        # 1
    if not has_agent and has_git:
        return Mode.MID_PROJECT  # 2
    if has_agent and not has_version:
        return Mode.PRE_V0_4     # 3 (legacy)
    version = read_version(repo_root)
    if version < CURRENT_SCHEMA_VERSION:
        return Mode.UPGRADE      # 3 (continuing)
    return Mode.CURRENT          # nothing to do
```

**Commands**

```bash
dotagent migrate                  # auto-detect; show preview; ask for confirmation
dotagent migrate --plan           # show what would change; do nothing
dotagent migrate --to 0.4.0       # explicit target
dotagent migrate --rollback       # undo last migration using .migration-log.md
```

**Migration log format**

```markdown
<!-- machine-readable; one line per change -->
# Migration log

## 2026-05-21T10:00:00Z · v0.3 → v0.4

- MOVED: `.agent/project/modules/01-auth/PLAN.md` → (unchanged, but reformatted)
- CREATED: `.agent/project_brief.md` (stub)
- CREATED: `.agent/.version` (`0.4.0`)
- INFERRED: `bug_id_prefix: BE` from existing `docs/bug-registry.md`
- ARCHIVED: 142 fixed bugs → `docs/archive/2025/bug-registry.md`
```

**Tests** (22)

- Mode detection: each of FRESH, MID_PROJECT, PRE_V0_4, UPGRADE, CURRENT
- v0.3 → v0.4 creates `.agent/.version`
- v0.3 → v0.4 creates brief stub
- v0.3 plan.yaml: new fields added; existing preserved
- Rollback restores original layout exactly
- Migration is idempotent (running twice changes nothing the second time)
- `--plan` produces output without touching files
- Bug-registry prefix inferred when consistent
- Bug-registry prefix asked interactively when ambiguous
- Migration aborts cleanly if `.git/` working tree is dirty
- Migration log is machine-readable
- Existing `.agent/architecture.md` preserved verbatim
- Existing modules preserved
- Mode 1 fresh install writes minimum required structure
- Mode 2 mid-project ingests existing `docs/*.md`
- Cross-tier migration (single-repo → service-repo + project-root creation) prompts user
- Migrate refuses if doctor reports a higher version than current dotagent
- Each step in migration log includes the original path so rollback can restore
- `--rollback` warns if log is missing or corrupt
- `dotagent doctor` after migrate reports clean
- Hidden `.agent/.cache/` excluded from migration
- Migration handles existing `.agent/.imported/` files (preserves them)

**Effort:** ~900 lines including tests
**Risk:** high — touches every existing user's filesystem
**Acceptance:** a v0.3 dotagent install upgrades cleanly to v0.4 with `dotagent migrate`, and `--rollback` reverses it bit-for-bit

---

### PR #3 — Archive command family + automatic triggers

**Goal:** explicit lifecycle for fixed bugs, rescinded anti-patterns, shipped modules.

**Files to create**

| Path | Purpose |
|---|---|
| `src/dotagent/archive/__init__.py` | Public surface: `scan`, `run`, `restore`, `list` |
| `src/dotagent/archive/triggers.py` | Per-source eligibility logic (bug-registry, anti-patterns, modules, deps) |
| `src/dotagent/archive/mover.py` | The atomic move + log writer |
| `src/dotagent/commands/archive_cmd.py` | `dotagent archive scan / run / restore / list` |
| `tests/test_archive_triggers.py` | 10 tests |
| `tests/test_archive_mover.py` | 6 tests |
| `tests/test_archive_restore.py` | 4 tests |

**Files to modify**

| Path | Change |
|---|---|
| `src/dotagent/doctor.py` | Add `_check_archive_eligible()` that reports pending count |
| `src/dotagent/commands/doctor_cmd.py` | Surface pending archive count |
| `src/dotagent/paths.py` | Add `archive_dir`, `archive_year_dir(year)`, `archive_log` |

**Archive log format**

```markdown
# Archive log

## 2026-05-21T10:00:00Z · automatic run

- BUG-007: bug-registry.md → docs/archive/2025/bug-registry.md (fixed: 2025-09-15, frozen: 2025-09-20, archived: 2026-05-21)
- BUG-014: bug-registry.md → docs/archive/2025/bug-registry.md (fixed: 2025-11-02)
- AP-003: anti-patterns.md → docs/archive/2025/anti-patterns.md (rescinded: 2025-12-01, "no longer applies after Postgres 16 upgrade")
```

**Commands**

```bash
dotagent archive scan             # read-only; report what's eligible
dotagent archive scan --json
dotagent archive run              # execute; prompts for confirmation
dotagent archive run --dry-run
dotagent archive run --since 30d  # custom trigger window
dotagent archive list             # show what's been archived
dotagent archive restore <id>     # un-archive (false positive recovery)
```

**Tests** (20)

- Trigger for bug-registry: status=fixed AND fix-frozen-30d-ago → eligible
- Trigger for bug-registry: status=fixed AND fix-frozen-15d-ago → NOT eligible
- Trigger for anti-patterns: rescinded=true → eligible immediately
- Trigger for modules: shipped + last-cycle-frozen-90d → eligible
- Trigger for deps: component removed flag → eligible
- `scan` produces stable JSON output
- `run` is atomic: failure mid-move leaves no partial state
- `run` writes to log
- `restore` reads log + reverses one entry
- `restore` updates log entry as `restored: 2026-05-22 by alice`
- Restored entry can be re-archived
- `--dry-run` produces same output as `run` but no filesystem changes
- Multiple archive runs in same day go to same archive file (appended)
- New year creates new archive year-dir
- `list` filters by source / year / status
- Custom trigger window honored
- Archived bugs still parseable by the bug-registry indexer
- Restored bugs reappear in CLAUDE.md immediately on sync
- Archive operations recorded in episodic memory (so `who --file docs/bug-registry.md` shows them)
- Doctor reports `info` (not warn/error) when archive count > 0

**Effort:** ~500 lines including tests
**Risk:** medium — touches existing user content; needs atomic-move discipline
**Acceptance:** running `dotagent archive run` on a year-old repo with mixed-status bugs cleanly moves only the fixed ones

---

### PR #4 — Bug registry tiering + prefix declaration

**Goal:** `bug_id_prefix:` declared per repo; tiered registries (Project Root + per-repo); cross-references work.

**Files to modify**

| Path | Change |
|---|---|
| `src/dotagent/config.py` | Accept `bug_id_prefix: <prefix>` field |
| `src/dotagent/sources.py` | Bug-registry parser respects prefix; cross-reference detection (entry body contains `<other-prefix>-NNNN`) |
| `src/dotagent/adapters/render.py` | CLAUDE.md surfaces top N this-repo bugs + cross-service summary |
| `src/dotagent/doctor.py` | Add `_check_bug_prefix_collisions()` (project-root scans all child config.yaml files when manifest present) |
| `tests/test_bug_registry_tiering.py` | 8 tests |

**Cross-reference format**

In Project Root `docs/bug-registry.md`:
```markdown
## AGT-0042 · Auth token leak across tenants (HIGH)
Status: open
Affected services: backend (BE-0123), customer-portal (PORTAL-0089)
Steps to reproduce: ...
```

In backend `docs/bug-registry.md`:
```markdown
## BE-0123 · Auth manifests as 401-loop in /chat
Status: open
Cross-reference: see AGT-0042 (Project Root)
```

`dotagent sync` walks `BE-0123 → AGT-0042` and surfaces it in backend's CLAUDE.md as "this bug is part of cross-service AGT-0042 — coordinate fix."

**Tests** (8)

- Prefix declared in config → parser uses it
- Prefix missing in config → uses sources `_default_bug_prefix` (today's behavior, backward compat)
- Cross-reference to AGT-### detected in body
- Cross-reference surfaces in CLAUDE.md
- Prefix collision (two repos declare same prefix) → doctor warns
- Cross-tier rollup: project-root CLAUDE.md aggregates child cross-references
- Backward compat: a v0.3 repo with no prefix declared still renders correctly
- Bug-registry archive scan respects tier (a project-root bug isn't archived just because backend's slice is fixed)

**Effort:** ~300 lines including tests
**Risk:** low — additive to existing parser
**Acceptance:** in a layered project, fixing a cross-service bug is recorded once at project-root with references in each affected service

---

### PR #5 — `project_brief.md` scaffolding + commands

**Goal:** introduce the brief file, its data model, the four commands to manage it.

(Same content as v1 plan's PR #12 — locked template, parser + renderer, `init / upload / show / edit`. Skipping the duplicate detail here; see chat history for the locked template.)

**Effort:** ~600 lines including tests

---

### PR #6 — FEAT/OBJ/RULE wiring + traceability checker + S11

**Goal:** plan and contracts cite brief IDs; `dotagent project brief check` audits the chain; S11 rubric signal enforces business-traceability.

(Same as v1 plan's PR #13 — see chat for detail.)

**Effort:** ~500 lines including tests

---

### PR #7 — CLAUDE.md renders brief subset (per-repo filtered)

**Goal:** each repo's CLAUDE.md includes the structured subset of the brief (OBJs, this-repo's FEATs, hard rules, glossary, tenancy, non-goals).

(Same as v1 plan's PR #14.)

**Effort:** ~200 lines including tests

---

### PR #8 — Per-repo `CONTRACTS.md` (Tier 2)

**Goal:** auto-generated, module-grouped contracts dashboard at `.agent/project/CONTRACTS.md` in every repo.

(Same as v1 plan's PR #9.)

**Effort:** ~250 lines including tests

---

### PR #9 — Plan negotiation primitives

**Goal:** introduce the dev↔QA negotiation pattern for `plan.yaml` itself, as **pure data ops**. **dotagent has no Planner/QA concept internally — those are roles an orchestrator (Coda, a human, a script) assigns via the `--actor` flag.**

**Files to create**

| Path | Purpose |
|---|---|
| `src/dotagent/project/plan_negotiation.py` | `write_draft`, `write_review`, `advance_round`, `diff`, `is_converged`, `freeze` |
| `src/dotagent/commands/plan_cmd.py` | `dotagent project plan {write-draft \| write-review \| diff \| converged \| freeze \| show}` |
| `tests/project/test_plan_negotiation.py` | 14 tests parallel to contract negotiation tests |

**Files to modify**

| Path | Change |
|---|---|
| `src/dotagent/paths.py` | Add `plan_negotiations_dir`, `plan_draft_path`, `plan_frozen_path`, `plan_round_dir` |
| `src/dotagent/project/model.py` | Optional `Plan` dataclass (more structured than current `Project`) |
| `src/dotagent/cli.py` | Register `plan` subgroup |

**Command signatures (Coda-friendly)**

```bash
# Coda reads, then writes via these. No LLM in dotagent.
dotagent project plan write-draft  --actor <name> --from-stdin
dotagent project plan write-review --actor <name> --from-stdin --rationale "<text>"
dotagent project plan diff          --format json
dotagent project plan converged                   # exit 0 if converged, 1 otherwise
dotagent project plan freeze       [--force --rationale "<text>"]
dotagent project plan show         [--draft] [--format json|yaml]
dotagent project plan log          [--since-round N] [--format json|markdown]
```

The `--actor` flag is opaque to dotagent. Any string. Coda passes `planner` / `qa`. A human passes their identity. dotagent only checks that consecutive rounds come from different actors (so same-actor refines a round, alternating actors advance the counter).

**File layout (added)**

```
.agent/project/
├── plan.yaml                       (in-effect plan; existing)
├── plan.frozen.yaml                (snapshot from last freeze)
└── plan-negotiations/
    └── 01/
        ├── plan.draft.yaml         (live working doc)
        ├── negotiation-log.md      (every round + rationale)
        └── rounds/
            ├── 01-<actor>.yaml
            ├── 02-<actor>.yaml
            └── ...
```

**Tests** (14)

- Empty initial state → `write-draft` opens round 1
- Two distinct actors alternating → rounds advance
- Same actor re-writes → round stays the same (refinement)
- Content-hash convergence: two consecutive rounds (different actors) with identical hashes → converged
- `is_converged` exits 0 / 1 correctly
- Freeze refuses if not converged (without --force)
- `--force` records the rationale in negotiation log
- Idempotent re-freeze is a no-op returning the existing frozen path
- `--json` outputs stable shape
- Diff between rounds shows changes
- Log shows round number, actor, timestamp, hash, optional rationale
- Cross-round restore (e.g., user wants to revert to round 2 of round 5) → tested via tooling docs (not a separate command in this PR)
- Schema validation on draft refuses missing required fields
- Negotiations dir created lazily on first write

**Effort:** ~700 lines including tests
**Risk:** medium-high — new state machine; large test surface
**Acceptance:** Coda can drive 6 calls to converge a plan; no LLM inside dotagent

---

### PR #10 — Auto-generated Modules table inside `project_brief.md`

(Same as v1 plan's PR #16.)

**Effort:** ~150 lines including tests

---

### PR #11 — `parent:` field + repo manifest

(Same as v1 plan's PR #10.)

**Effort:** ~400 lines including tests

---

### PR #12 — Cross-repo `contracts.md` rollup (Tier 1)

(Same as v1 plan's PR #11.)

**Effort:** ~250 lines including tests

---

### PR #13 — `git.yaml` + meta sync commands

**Goal:** Project Root knows where it lives in git; meta content syncs via `dotagent git push / pull / status`.

(Same as v1 plan's PR #18, with the correction that branch reservation only applies to the **meta repo's `main`** — service repos' `main` is normal.)

**Effort:** ~500 lines including tests

---

### PR #14 — Branch reservation enforcement (meta repo only)

**Goal:** prevent code from landing on the meta repo's branches; prevent any push to the meta repo's `main`.

**Critical scope correction:** service repos (`aigent-backend`, `aigent-portal`, `aigent-admin`) are NOT touched. Their `main` is the normal code branch and is unrestricted. Enforcement applies only to the meta repo.

**Files to create**

| Path | Purpose |
|---|---|
| `src/dotagent/scaffolds/branch_rules.yml.j2` | GitHub Actions workflow (installed in meta repo only) |
| `src/dotagent/scaffolds/pre-push-meta.sh` | Local pre-push hook (installed in meta repo clone only) |
| `tests/test_branch_rules.py` | 10 tests |

**Files to modify**

| Path | Change |
|---|---|
| `src/dotagent/commands/git_cmd.py` | Add `init-hooks`, `scaffold-protection`, `verify`. Each command verifies it's being run from the meta repo before installing. |

**Tests** (10)

- Verify passes on a clean meta push (only .agent/, docs/, *.md)
- Verify fails on Python file in meta push
- Verify against locked `main` rejects everything
- `init-hooks` refuses to install in a service repo (detects via `git.yaml::strategy`)
- `init-hooks` warns on the meta repo's clone if `main` policy is `locked`
- `scaffold-protection` writes valid GitHub Action YAML
- Multiple branch rules apply correctly
- Pre-push hook is idempotent
- Exit codes consistent across commands
- Documentation explicitly notes "service repos are NOT affected"

**Effort:** ~350 lines including tests
**Risk:** medium — git hook installation is platform-sensitive
**Acceptance:** pushing `auth.py` to `aigent-meta::dotagent/meta` is rejected; pushing `auth.py` to `aigent-backend::main` is unaffected

---

## Total effort

| Phase | PRs | Estimated lines (code + tests) |
|---|---|---|
| 0 | #1, #2 | ~1,500 |
| 1 | #3, #4 | ~800 |
| 2 | #5, #6, #7 | ~1,300 |
| 3 | #8 | ~250 |
| 4 | #9, #10 | ~850 |
| 5 | #11, #12 | ~650 |
| 6 | #13, #14 | ~850 |
| **Total** | **14** | **~6,200** |

At a sustainable pace, this is **6–8 weeks of focused work** including review cycles.

---

## Release plan

| Version | Phases included | What ships |
|---|---|---|
| **v0.4.0** | 0, 1, 2 | Canonical schema + migration + archive policy + bug-tiering + brief + traceability + CLAUDE rendering |
| **v0.5.0** | 3, 4 | Per-repo CONTRACTS.md + plan negotiation + brief modules table |
| **v0.6.0** | 5 | Layered structure + cross-repo rollup |
| **v0.7.0** | 6 | Git layout + meta-only enforcement |

Each release is tagged in git (`v0.4.0`, etc.) and the schema version (`.agent/.version`) is bumped at the start of each release's first PR.

---

## Risks + mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Migration (PR #2) corrupts existing user content | low | catastrophic | Mandatory rollback log; atomic moves; refuse to run on dirty working tree; mandatory `--plan` preview before run |
| Canonical schema becomes a maintenance burden | medium | medium | Schema is data-driven (table of entries); adding a new file is one line + one test |
| Layered context (PR #11) introduces sync cycles | medium | high | Cycle detection lint; depth capped at 3 levels |
| Plan negotiation log gets large for slow-converging plans | low | low | Compression on freeze (rounds older than freeze archived) |
| GitHub branch protection requires admin perms | high | low | Docs explicitly call this out; provide manual steps; `dotagent git scaffold-protection` prints what to click |
| Brief upload (PR #5) gets demand for PDF/DOCX | high | low | Markdown-only in v1; defer to a post-v0.7 PR with explicit LLM extraction risks documented |
| `parent:` field becomes recursion footgun | low | medium | Depth cap; cycle detection in tests |
| Cross-service modules drift between repos | medium | medium | `dotagent project brief check` audits cross_module references |
| Archive trigger misclassifies | medium | medium | Reversible via `archive restore`; `--dry-run` always available; trigger windows configurable |
| Bug prefix collisions across repos | medium | low | `dotagent doctor` warns; interactive resolution on `dotagent migrate` |
| User runs migration on production-grade repo without backup | high | catastrophic | Migration refuses on dirty git tree; mandatory `--plan` preview; log written before any move |

---

## Backward compatibility commitments

1. **Existing single-repo dotagent users keep working.** No `parent:`, no brief, no rollup → identical v0.3 behavior. PR #2 migrate is opt-in.
2. **The 230 existing tests must remain green.** Any test that breaks needs an explicit justification in the PR.
3. **Generated files keep their existing names.** `CLAUDE.md`, `.cursorrules`, `AGENTS.md`, `.github/copilot-instructions.md` — same names, additive sections only.
4. **`dotagent --version`'s output format unchanged.**
5. **`dotagent doctor` exit codes unchanged**: 0 on clean, 1 on any fail. New checks slot into the existing framework.

---

## Approval gates

Before any code is written, the user (you) approves:

1. **Decision lock-in (D1-D10 above)** — anything you want to revise?
2. **PR sequencing** — start with Phase 0 (PR #1 → PR #2), then Phase 1 (PR #3, #4), then ship v0.4.0?
3. **Release cadence** — ship per-PR (v0.4.1, v0.4.2, ...) or ship per-phase (v0.4.0 once all of Phase 0+1+2 lands)?
4. **Risk acceptance on PR #2 (migrate)** — proceed knowing it touches existing-user filesystems, mitigated by `--plan` preview + rollback log?
5. **Anything in this list to defer past v0.7?**

Once approved, the plan is locked. I'll start with PR #1 and post incremental progress.

---

## Decisions still open

These weren't fully resolved in chat and need a call before PR #5 / PR #6 work:

1. **Brief in markdown only (v1) or also PDF/DOCX?** Recommendation: markdown only; LLM PDF extraction in v2.
2. **Module IDs auto-assigned (M01, M02, ...) by plan order, or human-chosen slugs?** Recommendation: auto-assigned numerics; slug stored as the module's `name` field.
3. **When Coda writes via `plan write-draft --from-stdin`, does dotagent validate the YAML shape on every write or only on freeze?** Recommendation: validate on every write so Coda gets fast feedback; freeze re-validates as a safety net.
4. **Archive default trigger window for bugs:** 30 days or configurable per-repo? Recommendation: 30 days default, override via `.agent/config.yaml::archive.bug_min_age_days`.

---

## Appendix A — Canonical structure (complete tree)

(See the file structure tree in chat history; locked. Repeat-listed here as a single authoritative reference once approved.)

## Appendix B — Project brief template (complete)

(See the template in chat history; locked.)

## Appendix C — Plan.yaml schema (locked from chat)

```yaml
name: <project-name>
goal: "<one-line project goal>"
brief: ../project_brief.md
brief_version: <integer>
brief_objectives_covered: [OBJ-NN, ...]
brief_features_covered:   [FEAT-NN, ...]
repos:
  - id: <slug>
    path: ./<dir>
    remote: <git url>
    default_branch: main
    role: <api | frontend | backoffice | ...>
features_to_modules:
  FEAT-NN: [M01, M02, ...]
modules:
  M01: { repo: <id>, owner: <name>, deps: [], state: planned, integrations: [] }
success_criteria:
  - { id: SC-NN, text: "...", serves: [OBJ-NN] }
tools:
  development: { tool: <name>, model: "" }
  qa:          { tool: <name>, model: "" }
  review:      { tool: <name>, model: "" }
  planning:    { tool: <name>, model: "" }
created_at: <iso>
updated_at: <iso>
```

## Appendix D — git.yaml schema (locked from chat)

```yaml
meta:
  strategy: dedicated_repo
  remote: git@github.com:<owner>/<meta-repo>.git
  branch: dotagent/meta              # never main
  main_branch_policy: locked         # ONLY for the meta repo; service repos unaffected
repos:
  - id: <slug>
    path: ./<dir>
    remote: <git url>
    default_branch: main             # NORMAL — not locked
    role: <api | frontend | ...>
branch_rules:
  - remote: git@github.com:<owner>/<meta-repo>.git
    branches:
      main:
        allowed_paths: []
        forbidden_paths: ["**/*"]
        description: "Reserved. Use dotagent/meta for meta content."
      dotagent/meta:
        allowed_paths: [".agent/", "docs/", "*.md"]
        forbidden_paths: ["**/*.py", "**/*.ts", "**/*.tsx", "**/Dockerfile", "**/*.sql"]
        description: "Meta content only — never code."
```

---

## Sign-off

When you approve this plan:

- Reply with "approved" + answers to the four open decisions in section _Decisions still open_
- I'll merge this `IMPLEMENTATION_PLAN.md` to main on a fresh PR (separate from execution)
- I'll start PR #1 immediately after; subsequent PRs follow the dependency graph
