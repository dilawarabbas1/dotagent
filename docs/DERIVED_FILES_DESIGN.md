# Derived files — what dotagent generates and why

_Status: locked as of v0.4.10 · last updated 2026-05-20_

dotagent owns a small set of GENERATED files: views of project state
that are derivable from authoritative inputs. They re-render on every
`dotagent sync`, `dotagent project regenerate`, and pre-commit (when
`docs/*.md` changes). Hand-editing them is wasted effort — the edit
disappears on the next regen.

This document covers the three generators added in v0.4.10:

- `docs/service-registry.md`
- `.agent/project/modules/<id>/HISTORY.md`
- `.agent/dashboard.md`

For the broader ownership model (dotagent writes GENERATED; Claude writes
CONTENT), see `CLAUDE_MD_DESIGN.md` § "Layer 2 — Workflow contract."

---

## TL;DR

| File | Source of truth | Tier | When to read |
|---|---|---|---|
| `docs/service-registry.md` | `.agent/git.yaml` `repos:` | project-root | navigating to a sibling service |
| `.agent/project/modules/<id>/HISTORY.md` | each module's `cycles/` dir + `completion.md` | any with modules | "what's happened in this module?" |
| `.agent/dashboard.md` | aggregated Project + episodic memory + doc mtimes | any | "what's the state of this project right now?" |

---

## `docs/service-registry.md`

**What:** one-page table of every service in a multi-repo project.

**Source:** `.agent/git.yaml`'s `repos:` block. Each entry contributes
one row: `id · path · default_branch · role · remote`.

**Why generated:** the data already exists in `git.yaml`. Maintaining a
parallel hand-written registry led to drift — service names diverged from
the actual repo ids, branch policies stayed stale after merges.

**Output shape:**

```markdown
| Service        | Path             | Default branch | Role          | Remote       |
|----------------|------------------|----------------|---------------|--------------|
| aigent-portal  | customer-portal/ | main           | Customer UI   | git@...      |
| aigent-backend | backend/         | main           | API + workers | git@...      |
| aigent-admin   | admin/           | main           | Admin tools   | git@...      |
```

**Tier:** project-root only. Single-repo and service-repo tiers don't
own a registry (single-repo has nothing to register; service-repo
inherits from `../docs/service-registry.md`).

**Inherited reference:** the service-repo schema entry
`../docs/service-registry.md` is now marked `KIND_GENERATED` so the
manifest's INHERITED marker is honest.

---

## `.agent/project/modules/<id>/HISTORY.md`

**What:** per-module cycle log — one block per cycle with status, dates,
contract round, QA outcome, files changed.

**Source:** the `Module` object as loaded from `module.yaml` + its cycle
artifacts (`cycles/<NN>/contract.frozen.md`, `dev-handoff.md`,
`qa-findings.md`).

**Why generated:** today the cycle data is scattered across 4–5 files
per cycle, sometimes spanning 20+ cycles on a mature module. Nobody can
answer "what's the history of this module?" without manually walking
the directory tree. HISTORY.md is the rollup.

**Cycle ordering:** newest first. The most-relevant entry is at the top
so a reader doesn't have to scroll.

**Status badges:**
- `✓ Passed QA`
- `✗ Failed QA`
- `⏳ Contract frozen — implementation / QA pending`
- `⏳ Dev handoff — awaiting QA`
- `📝 Contract negotiation (round N/M)`
- `🟢 In progress` (started, no contract yet)

**Tier:** any project that has modules (project-root, single-repo).
Service-repo has its own modules under `.agent/project/modules/` too,
so it renders local HISTORY.md per module.

---

## `.agent/dashboard.md`

**What:** project health snapshot. Single page, five sections:

1. **📜 Open contracts** — modules whose current cycle has a non-frozen
   or freshly-frozen contract (i.e. QA hasn't recorded `pass` yet).
2. **🧪 Pending QA** — dev-handoff received but no QA result recorded.
3. **⏰ Stalled (>14d)** — active cycles whose last activity timestamp
   is older than the threshold.
4. **📅 Doc staleness (>60d)** — canonical docs/ files (bug-registry,
   anti-patterns, architecture, redis-keys, db-impact-map, dependency-map)
   whose mtime is older than the threshold.
5. **📡 Recent activity** — last 10 events from episodic memory.

**Source:**
- Open / pending / stalled: walks `project.modules` and inspects each
  module's `current_cycle` (`Contract.status`, `Cycle.handoff_at`,
  `QAResult`).
- Doc staleness: filesystem `mtime` per file.
- Recent activity: `EpisodicMemory(paths).iter_events()` reversed +
  trimmed.

**Why generated:** until now there was no single answer to "is anything
on fire?" — you had to open SCOPE.md, CONTRACTS.md, every module dir,
and the activity feed separately. The dashboard is the daily-standup
view in one file.

**Tier:** project-root tier surfaces project-wide state; service-repo
tier surfaces this-service-only state (since the loaded Project is
service-scoped). Single-repo renders the same way.

**Inherited reference:** service-repo manifest carries an inherited
pointer to `../.agent/dashboard.md` so the AI knows where the
cross-service rollup lives.

---

## Wiring

All three are dispatched through `regenerate_derived_files(paths)` in
`src/dotagent/render/derived.py`, which is called from:

| Call site | When |
|---|---|
| `dotagent sync` | adapter regen step |
| `dotagent project regenerate` | explicit |
| `dotagent observe pre-commit` | when staged files include `docs/*.md` |

Each generator is wrapped in a try/except inside the orchestrator:
**one generator failing never blocks the others.** Failures go to
`.agent/log/` via `log_exception()`; the command keeps going.

`regenerate_derived_files()` is safe to call from any state:
- no `.agent/` → returns `[]`
- no `git.yaml` → skips service-registry, still writes dashboard if a
  project exists
- no `plan.yaml` → skips HISTORY + dashboard, still writes
  service-registry if `git.yaml` exists

---

## Output guarantees

Each file starts with a banner:

```
<!-- generated by dotagent · <kind> · do not hand-edit (edit <source> instead) -->
<!-- rendered-at: <ISO> · <metadata> -->
```

- `<kind>` identifies the generator.
- `do not hand-edit` points the human at the actual source of truth.
- `rendered-at` makes drift detection trivial (`grep rendered-at:`
  across files; if one's much older, something's broken in the
  pipeline).

The banners follow the same pattern as the existing CLAUDE.md,
SCOPE.md, CONTRACTS.md, etc. — so anything that recognizes "dotagent
banner = generated" continues to work.

---

## Schema integration

Schema entries (`canonical_structure.py`):

```python
# project-root tier
SchemaEntry("docs/service-registry.md", kind=KIND_GENERATED,
            category=CAT_ARCHITECTURE, when_to_read="GENERATED · ...")

SchemaEntry(".agent/project/modules/<id>/HISTORY.md", kind=KIND_GENERATED,
            category=CAT_CONTRACTS, when_to_read="GENERATED · ...")

SchemaEntry(".agent/dashboard.md", kind=KIND_GENERATED,
            category=CAT_PRIORITIES, when_to_read="GENERATED · ...")

# single-repo tier — same three (no service-registry, has the other two)
# service-repo tier — local HISTORY + dashboard;
#                     inherits service-registry + dashboard from parent
```

The CLAUDE.md manifest renderer surfaces all three under their assigned
categories (`Architecture`, `Active contracts + cycles`, `Active right now`).

The coverage gates (`test_manifest_coverage.py`) confirm every new
entry renders. If you add another generator, declare its schema entry
with a category — coverage CI will fail otherwise.

---

## What this design does NOT do

1. **No partial regen on file-level diff.** Each generator re-renders
   its full output every call. For 100+ modules this might matter; for
   typical projects it's irrelevant (sub-second).

2. **No "what would change" preview.** `dotagent project regenerate
   --dry-run` shows path names but not diffs. Future work if needed.

3. **No git auto-staging.** Regenerated files land on disk but are not
   `git add`-ed. The developer decides what's part of the commit.

4. **No history of dashboards.** Each render overwrites the previous.
   Episodic memory holds the history; dashboard is the current view.

---

## Related docs

- `CLAUDE_MD_DESIGN.md` — overall ownership model + manifest design.
- `SERVICE_REPO_CLAUDE_MD.md` — service-repo as child of project-root.
- `src/dotagent/render/derived.py` — the orchestrator.
- `src/dotagent/render/{service_registry,module_history,dashboard}.py` —
  the three generators.
- `tests/render/test_{service_registry,module_history,dashboard,derived_regen}.py`
  — 32 tests covering the generators + their integration.
