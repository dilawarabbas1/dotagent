# Service-repo CLAUDE.md — child-of-project-root design

_Status: locked as of v0.5.0 · last updated 2026-05-20_

This document explains the **service-repo tier** of dotagent's CLAUDE.md:
what it is, why it's distinct from the project-root and single-repo tiers,
and how it acts as a *child* of the project-root layer.

For the general CLAUDE.md design philosophy (the four layers, navigation
manifest vs compendium, ownership rule), see `CLAUDE_MD_DESIGN.md`. This
document only covers what is **specific to service-repo tier**.

For the implementation, see:
- `src/dotagent/canonical_structure.py` — `_SERVICE_REPO_ENTRIES`
- `src/dotagent/render/manifest.py` — `render_manifest(..., tier="service-repo")`

---

## TL;DR

A service-repo CLAUDE.md is a **child manifest** that:

1. Surfaces this service's local context (`.agent/`, `docs/`, modules).
2. Surfaces the parent project-root's context via `../`-prefixed pointers,
   each tagged **INHERITED** so the AI knows precedence.
3. Renders the contract layer (`.agent/project/modules/<id>/cycles/<NN>/`)
   prominently — every service has its own dev↔QA cycles, even when those
   cycles are slices of a cross-service module.
4. Points outward to sibling services via `../docs/service-registry.md`
   so the AI can navigate the topology, not memorize it.

A single-repo CLAUDE.md has no parent and no inheritance. A project-root
CLAUDE.md is the parent and has no `../` references. A service-repo
CLAUDE.md is the *only* tier where inheritance is rendered explicitly.

---

## The three tiers, side by side

| Aspect | project-root | service-repo | single-repo |
|---|---|---|---|
| Lives where? | Meta repo (e.g. `Aigent/`) | Service repo (e.g. `aigent-portal/`) | Standalone repo |
| Parent? | None | `../` (the project root) | None |
| Detected by | `.agent/git.yaml` present | `parent:` in `.agent/config.yaml` | Neither |
| Renders `../` pointers? | Never | Always | Never |
| Renders cross-service rollups? | Yes (it owns them) | As inherited pointers | N/A |
| Bug registry scope | Cross-service (`AGT-####`) | Service-local (`BE-####`, `PT-####`) | Project bugs |
| Modules scope | Cross-service master modules | This service's slices | All modules |

The same renderer (`render_manifest`) handles all three; the schema entries
differ per tier, which is what drives the structural difference in output.

---

## Why a service repo needs its own CLAUDE.md at all

In a multi-service project (Aigent has 5+ services), each service repo
is its own git checkout — different developers may have only one repo
cloned at a time, AI sessions are often scoped to a single repo, CI runs
per-repo. So each service needs a CLAUDE.md that:

1. **Stands on its own** for a session that only sees this one repo.
2. **Knows it's not alone** — surfaces enough parent context that the AI
   doesn't make decisions that violate cross-service contracts.
3. **Points to the parent** for cross-cutting concerns rather than
   duplicating them (no copy-pasting `rules.md` into every service).

The service-repo CLAUDE.md is the *bridge* between "this repo's local
state" and "the project-wide truth that lives one directory up."

---

## What the service-repo CLAUDE.md contains

The same four-layer structure as project-root and single-repo:

```
Layer 1 — How to read this file       (invariant)
Layer 2 — Workflow contract           (invariant; same OWNERSHIP RULE)
Layer 3 — Hard policy                 (invariant)
Layer 4 — Navigation manifest         (tier-specific — this is where it differs)
```

Layers 1–3 are byte-identical to the other tiers. The difference is in
Layer 4: **the schema entries that get rendered**.

### Layer 4 — what's in a service-repo manifest

The schema (`_SERVICE_REPO_ENTRIES` in `canonical_structure.py`) declares
three groups of entries:

#### Group A — Local pointers (this service's files)

These point at files in this repo and follow the same conventions as
single-repo. Examples:

```
.agent/project_brief.md       # this service's brief (optional)
.agent/rules.md               # this service's hard rules (ADD to project's)
.agent/architecture.md        # this service's architecture (concise)
.agent/style.md               # this service's code style
.agent/project/plan.yaml      # this service's plan slice
.agent/project/CONTRACTS.md   # this service's contracts dashboard
docs/bug-registry.md          # service-local bugs (BE-####, PT-####, ...)
docs/redis-keys.md            # service-local Redis namespaces
docs/db-impact-map.md         # service-local DB tables
docs/architecture.md          # service-local architecture (long-form)
docs/anti-patterns.md         # service-local anti-patterns
docs/dependency-map.md        # intra-service module graph
```

#### Group B — Contract layer (cycle artifacts)

The dev↔QA cycle artifacts get rendered with their full path patterns
so the AI knows the exact filenames it'll encounter:

```
.agent/project/modules                                          (DIR)
.agent/project/modules/<id>/module.yaml                         (FILE)
.agent/project/modules/<id>/PLAN.md                             (GENERATED)
.agent/project/modules/<id>/cycles/<NN>/contract.md             (FILE — live)
.agent/project/modules/<id>/cycles/<NN>/contract.frozen.md      (GENERATED — immutable)
.agent/project/modules/<id>/cycles/<NN>/dev-handoff.md          (FILE — via CLI)
.agent/project/modules/<id>/cycles/<NN>/qa-findings.md          (FILE — via CLI)
.agent/project/modules/<id>/completion.md                       (FILE)
```

These are templated paths (with `<id>`, `<NN>`). The renderer prints them
verbatim — the AI is smart enough to substitute. The point is to declare
the *shape* of the path so the AI knows what to read when the contract
phase starts.

A key sentence appears in the `.agent/project/modules` description:

> If `module.yaml` declares `cross_module: <project-root-module>`, this
> is a SLICE of a cross-service module — coordinate via the parent's
> cycle contract.

This is how cross-module slices are discovered: the AI sees a module.yaml
with a `cross_module:` field and knows to look at the parent's cycle.

#### Group C — Inherited pointers (project-root context)

This is the bit that's unique to service-repo. Every entry is
`../`-prefixed and its description starts with **`INHERITED ·`** so the
AI can visually distinguish parent context from local context:

```
../.agent/project_brief.md            INHERITED · business intent for the WHOLE project
../.agent/rules.md                    INHERITED · project-wide hard rules. Your service ADDs; never overrides.
../.agent/git.md                      INHERITED · branch policy + push rules for the meta repo
../.agent/architecture.md             INHERITED · whole-project technical architecture
../.agent/style.md                    INHERITED · project-wide style baseline. Service overrides where disagreeing.
../.agent/patterns.md                 INHERITED · project-wide patterns
../.agent/git.yaml                    INHERITED · git topology + branch rules
../.agent/project/plan.yaml           INHERITED · PROJECT-WIDE plan: features_to_modules, repos manifest
../.agent/project/SCOPE.md            INHERITED · human-readable project blueprint
../.agent/project/CONTRACTS.md        INHERITED · project-root contracts dashboard (cross-service modules)
../.agent/project/modules             INHERITED · CROSS-SERVICE modules at the project-root tier
../contracts.md                       INHERITED · Tier-1 cross-repo contracts rollup
../docs/service-registry.md           INHERITED · what each service does. Start here when navigating siblings.
../docs/shared-contracts.md           INHERITED · API/event schemas BETWEEN services
../docs/dependency-map.md             INHERITED · CROSS-SERVICE dependency graph
../docs/architecture.md               INHERITED · whole-project architecture (long form)
../docs/bug-registry.md               INHERITED · cross-service bugs (AGT-####). BE-#### bugs may cross-ref these.
../docs/anti-patterns.md              INHERITED · project-wide anti-patterns
```

The renderer groups these by **category alongside their local equivalents**.
For example, the rendered Style + conventions section looks like:

```markdown
## 🎨 Style + conventions

- `.agent/style.md` — Service-specific code style.
- `.agent/patterns.md` — Service-specific patterns.
- `.agent/preferences.md` — Service-specific team preferences.
- `../.agent/style.md` — INHERITED · project-wide style baseline. Your service style overrides where it disagrees.
- `../.agent/patterns.md` — INHERITED · project-wide patterns.
```

Local first, then inherited — the AI reads top-down and gets the precedence
visually.

---

## Locked design defaults

When designing the service-repo CLAUDE.md, four choices were locked:

1. **Hybrid contract re-statement.** The service-repo doesn't *duplicate*
   the project root's contracts inline. Instead it points at both layers
   (`.agent/project/CONTRACTS.md` for service-local, `../contracts.md` for
   cross-repo) and lets the AI read both. Cheaper to maintain; no drift.

2. **Cross-module slices are prominent.** The `.agent/project/modules`
   entry explicitly calls out that `cross_module:` slices coordinate via
   the *parent's* cycle contract. This means a developer working on a
   service-local feature never confuses it with a cross-service feature.

3. **Service-first bug registry with cross-ref pointer.** When you fix a
   bug, you update `docs/bug-registry.md` in this repo (service-local
   prefix like `BE-####`). The inherited pointer to `../docs/bug-registry.md`
   lets you cross-reference an `AGT-####` cross-service bug *from* your
   `BE-####` entry, not the other way around. Ownership stays clear.

4. **Mention `../docs/service-registry.md` and let the AI navigate.**
   We don't enumerate every sibling service in the manifest — that would
   be duplicate maintenance. The service registry is the single source of
   truth; the manifest just points there.

---

## Render output (excerpt)

A minimal service-repo render with `parent: ../meta` in `.agent/config.yaml`
produces sections like:

```markdown
## ⏰ What's active right now

- `.agent/project/CONTRACTS.md` — Open + frozen contracts dashboard for THIS service.
- `../.agent/project/CONTRACTS.md` — INHERITED · project-root tier contracts dashboard (cross-service modules).
- `../contracts.md` — INHERITED · Tier-1 cross-repo contracts rollup. See all services' state at a glance.

## 📜 Active contracts + cycles

- `.agent/project/modules` — Per-module directories. Each module: module.yaml + PLAN.md + cycles/. If `module.yaml` declares `cross_module: ...`, this is a SLICE of a cross-service module — coordinate via the parent's cycle contract.
- `.agent/project/modules/<id>/module.yaml` — Module state, implements_features, cross_module reference, cycles[].
- `.agent/project/modules/<id>/cycles/<NN>/contract.md` — LIVE contract under dev↔QA negotiation. Cite FEAT-NN + OBJ-NN in business-traceability.
- `.agent/project/modules/<id>/cycles/<NN>/contract.frozen.md` — IMMUTABLE post-freeze snapshot. Never edit. The agreement you implement against.
- `.agent/project/modules/<id>/cycles/<NN>/dev-handoff.md` — Dev says 'done' — written via `dotagent project handoff`. QA reads this next.
- `.agent/project/modules/<id>/cycles/<NN>/qa-findings.md` — QA pass/fail with MANDATORY rationale — written via `dotagent project qa-record`.
- `../.agent/project/modules` — INHERITED · CROSS-SERVICE modules at the project-root tier. If your service has a slice, the parent's cycle contract is authoritative.
```

This is the navigation index — the AI sees ~3K tokens of pointers and
chases what it needs. Not 50K tokens of inlined content.

---

## The generator

The generator is `render_manifest(paths, tier="service-repo")` in
`src/dotagent/render/manifest.py`. Tier auto-detection lives in
`detect_tier()` in `canonical_structure.py`:

```python
def detect_tier(repo: Path) -> str:
    """Detect tier from filesystem signals.

    - project-root: .agent/git.yaml present
    - service-repo: .agent/config.yaml has `parent:` field
    - single-repo: neither
    """
```

The renderer is dispatch-gated via `render.use_manifest` in
`.agent/config.yaml`:

```yaml
render:
  use_manifest: true   # v3 navigation manifest (will be default in v0.5.0)
```

When the flag is true, `resolve_body()` in `src/dotagent/adapters/_dispatch.py`
routes all adapters (CLAUDE.md, .cursorrules, copilot-instructions.md,
AGENTS.md) through `render_manifest()`. The same body lands in every
adapter file — different filenames, identical content.

To preview a service-repo render without writing files:

```bash
dotagent context              # if at service-repo tier, renders manifest
# or programmatically:
python -c "
from dotagent.paths import Paths
from dotagent.render.manifest import render_manifest
from pathlib import Path
paths = Paths(repo=Path('.'))
print(render_manifest(paths, tier='service-repo'))
"
```

To regenerate the on-disk CLAUDE.md (+ .cursorrules + copilot + AGENTS.md)
for this service:

```bash
dotagent sync                 # or `dotagent regenerate`
```

---

## CI guarantees

Three coverage gates enforce the design:

1. **Every schema entry has a category** (`test_every_schema_entry_has_a_category`)
   — no entry can default to `CAT_UNCATEGORIZED`.

2. **Every non-hidden schema entry appears in the rendered manifest**
   (`test_every_non_hidden_entry_appears_in_manifest`) — adding an entry
   to the schema also requires its category to be in the render order.

3. **Workflow contract + hard policy + reading protocol present in every
   tier's render** (`test_workflow_contract_present_in_every_manifest` +
   `test_hard_policy_ban_phrases_present`) — invariants can't silently
   regress.

Plus service-repo-specific tests in `tests/render/test_service_repo_child.py`:

- Every local contract-layer path is in the schema and renders.
- Every `../`-prefixed inherited path is in the schema and renders.
- The MUST_READ section includes the inherited project brief + rules + git.md.
- Inherited entries carry the `INHERITED` marker.

If any of these break, CI blocks merge.

---

## What this design does NOT do (yet)

1. **Doesn't read the parent's actual files at render time.** The renderer
   declares the pointer; it doesn't try to load `../.agent/project_brief.md`
   to enrich the manifest with parent content. That's intentional — the
   AI reads files on demand, so we don't need to embed the parent inline.

2. **Doesn't validate that parent files exist on disk.** The manifest is
   a navigation index, not a file-existence check. If the parent is missing,
   the pointer is a dead link — `dotagent doctor` flags that separately.

3. **Doesn't render different content based on `parent:` value.** All
   service-repo manifests get the same `../`-prefixed pointers, regardless
   of whether `parent:` is `../meta` or `../..`. The relative-path math
   is the AI's job, not the renderer's. (This is fine because the dominant
   case is `parent: ..` and the rest are rare.)

4. **Doesn't surface a per-service "what's mine vs what's shared" comparison.**
   Future work: when a service-repo has a cross-module slice, render a
   "🔀 Cross-module slices" callout at the top of the manifest. Tracked
   for v0.5.1.

---

## Related docs

- `CLAUDE_MD_DESIGN.md` — overall CLAUDE.md design (the four layers).
- `src/dotagent/canonical_structure.py` — schema definitions per tier.
- `src/dotagent/render/manifest.py` — the renderer.
- `src/dotagent/adapters/_dispatch.py` — v1↔v3 routing.
- `tests/render/test_service_repo_child.py` — service-repo-specific
  coverage gates.

If you change the schema or the renderer, update this document and
`CLAUDE_MD_DESIGN.md` in the same PR.
