# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic](https://semver.org/spec/v2.0.0.html).

## [0.5.5] — 2026-05-29

### Fixed — sharded sources now surface to the agent (real-world bug)

Large projects following the hand-maintained docs convention split a
single "kind" of source across multiple shards (e.g.
`docs/bug-registry-{agents,infrastructure,orchestrator}.md`,
`docs/db-impact-map-{master,tenant,vector}.md`,
`docs/redis-key-registry-{tenant,global,events}.md`) registered under
`sources.extra` with the same `kind`.

The Context accessors read only the single canonically-named source:

```python
src = self.sources.get("bug_registry")   # single key lookup
```

So every shard's parsed entries sat in `.agent/.cache/sources.json` +
pointer cards but **never reached the context the agent reads.**

**Measured on a real sharded project:**

| Accessor              | Before | After |
|-----------------------|------:|------:|
| `top_bugs`            |     2 |   533 |
| `top_anti_patterns`   |     0 |   242 |

The agent was reading a canonical stub that parsed to "no entries"
while 533 bugs + 242 anti-patterns lived in the shards, invisible.

### Implementation

- New `_iter_kind()` / `_entries_for_kind()` helpers in `context.py`
  aggregate across every source whose `.kind` matches (canonical +
  same-kind extras), deduped by `(id, title)`.
- The following accessors switch to the kind-aggregated reader:
  `top_bugs` · `top_anti_patterns` · `redis_keys` · `db_impact` ·
  `dependency_map` · `architecture_sections` · `hotspots_for_files` ·
  `detect_conflicts`.
- No config change needed for projects that already register shards
  under `sources.extra` with the right `kind`.

### Tests (+1)

`test_kind_aggregates_across_extra_shards` pins the behaviour: when
two shards declare the same kind, both contribute to the agent's
view. The accessor returns the union, deduped.

Full suite: **834 passed, 2 skipped.**

### Backward compat

- Single-canonical-source projects unchanged (the kind-aggregate
  helper falls through to the single source when no extras carry
  the same kind).
- No schema changes; no config changes; no breaking changes to any
  public API.

## [0.5.4] — 2026-05-26

### Added — dotgraph integration polish (six follow-ups from RedScope run)

Six additive items tightening the v0.5.3 dotgraph integration. Two
operator-gated decisions resolved as **(b)**:

1. **Multi-repo intelligence** — auto-pivot to `dotgraph workspace
   emit-docs --json` when `dotgraph-workspace.yml` is present at repo
   root. One subprocess call per workspace; aggregate JSON; dotagent
   doesn't parse workspace yml (except read-only in doctor). Falls
   back to single-repo flow when no workspace.yml.
2. **Doc-ownership boundary** — suffix-split layout. Dotgraph emits
   land under `docs/codegraph/` with a `.generated.md` suffix.
   Hand-maintained `docs/<name>.md` is preserved + patched ONCE with
   a reference link section to its generated counterpart.

### Specifically

- **`ensure_gitignored(repo_root)`** — pre-seeds `.gitignore` with
  `.dotgraph/` before the emit pre-step. Idempotent; variants
  tolerated.
- **`emit_docs` signature change** — returns `(ok, msg, payload)`;
  passes `--skip-empty --json` to dotgraph; legacy fallback for
  pre-0.1.10 dotgraph that doesn't know those flags.
- **`apply_codegraph_layout(repo)`** — renames freshly-emitted docs to
  `.generated.md`, patches hand-maintained files with a one-time
  reference marker (`<!-- dotagent: links to docs/codegraph/ -->`).
- **`workspace_status(repo)`** — read-only YAML parse + filesystem
  check for per-child-repo `.dotgraph/graph.db` existence. Used by
  doctor (no subprocess).
- **`workspace_index`, `workspace_emit_docs`** — wrappers for the
  dotgraph 0.1.11 workspace CLI; used by sync only.
- **`count_indexable_files(repo)`** — bounded walk that counts source
  files. Used for the "consider adding a workspace.yml" hint when
  meta has <20 files and no workspace.yml.
- **Stale alarm with reasons** — `DotgraphInfo` gains `stale_reasons:
  list[str]` and `stale_threshold_hours: int`. Doctor JSON exposes
  both. Default threshold 168h (7d), overridable via
  `dotagent.dotgraph.stale_threshold_hours` in config. Text mode
  emits an actionable hint when stale.
- **Awareness block lock** — regression test added that fails if the
  rendered "Code-graph awareness" section ever drops or adds a tool.
  Locked surface: exactly 5 (search · context_pack · impact ·
  reconcile · find_refs).

### Config knobs

`.agent/config.yaml`:

```yaml
dotagent:
  dotgraph:
    stale_threshold_hours: 168
    emit_docs:
      skip_empty: true
```

### Doctor JSON additions (all additive)

```json
"dotgraph": {
  "stale_reasons":         ["dirty_files", "last_indexed_too_old"],
  "stale_threshold_hours": 168,
  "workspace": {
    "yml_present": true,
    "repos": [{"name": "backend", "path": "...", "indexed": true}, ...]
  }
}
```

### Sync output additions

```
· added .dotgraph/ to .gitignore
· dotgraph emit-docs ok (3 written, 2 skipped: kafka-topics, ...)
· dotgraph workspace index ok                 (workspace flow)
· dotgraph workspace emit-docs ok (3 repo(s)) (workspace flow)
· patched 1 hand-maintained doc(s) with codegraph reference: ...
```

### Backward compat

- `doctor --format json` envelope unchanged; new fields are nested.
- `emit_docs` callers that destructure 2-tuple break. Only internal
  callers existed; updated. External callers should switch to the
  3-tuple `(ok, msg, payload)`.
- Projects with hand-maintained `docs/dependency-map.md` etc. keep
  working — they receive a one-time reference-link injection on the
  first sync, original content preserved verbatim below.

### Tests (+47 → 833 total)

- Awareness lock: +1
- Gitignore + emit-docs JSON + skip-empty: +11
- Stale alarm + reasons + threshold: +11
- Suffix-split layout: +7
- Workspace + count_indexable_files: +11
- Plus existing sync tests updated to reflect new file locations

Full suite: 833 passed, 2 skipped.

## [0.5.3] — 2026-05-21

### Added — dotgraph integration (schema + adapter + lifecycle)

dotagent now detects [dotgraph](https://github.com/dilawarabbas1/code-graph)
at render time and refreshes graph-derived docs during sync; doctor
reports the graph's freshness; the contract scaffold gained a
`## Surfaces` section that downstream gates can pipe into `dotgraph
reconcile`. Cycle orchestration and reconcile gating stay in the
consumer (Coda); dotagent only manages documents.

Three additive surfaces:

1. **Contract Surfaces schema.** Every freshly scaffolded `contract.md`
   carries a `## Surfaces` section with a fenced YAML block whose key
   names match dotgraph's `reconcile` flags verbatim (`tables`,
   `redis_keys`, `kafka_topics`, `collections`, plus `code` + `callers_to_update`
   + `tests_to_update`). Old contracts without it continue to validate
   and score — the anchor is optional, not in `SECTION_ANCHORS`.
   `dotagent project contract score --json` now emits
   `surfaces_enumerated` (count) and `surfaces_present` (bool)
   alongside the existing rubric — observability, not enforcement.
2. **Adapter "Code-graph awareness" block.** When `.dotgraph/graph.db`
   exists at the project root, every rendered adapter (CLAUDE.md,
   .cursorrules, copilot-instructions.md, AGENTS.md) gains a
   rules-of-engagement section listing the 5 dotgraph MCP tools
   (`context_pack`, `impact`, `reconcile`, `find_refs`, `search`) and
   the 5 static doc snapshots emit-docs maintains. Filesystem check
   only — render stays deterministic and never shells to dotgraph.
3. **Doctor + sync wiring.** `dotagent doctor --format json` now
   returns `{"diagnoses": [...], "dotgraph": {...}}` with version,
   db_present, dirty_files, stale, error. `dotagent sync` runs
   `dotgraph emit-docs --target all` as a pre-step when the db is
   present; opt out via `--skip-dotgraph`. Failures log and proceed.

### Deviations from the integration spec (resolved without help)

- `dotgraph status --json` does not expose `last_indexed`. Doctor
  emits `last_indexed: null`; `stale` is derived from `dirty_files > 0`
  alone when the timestamp is unavailable.
- `dotgraph reconcile` CLI has no `--claimed-callers` flag; the
  `callers_to_update:` YAML key in Surfaces is consumed via the MCP
  `reconcile` tool, not the CLI.

### Tests (+44)

- `tests/project/test_contract_surfaces.py` — 13 tests (parse, count,
  score, backward compat, content-hash)
- `tests/render/test_code_graph_awareness.py` — 13 tests (helper,
  manifest, v1, adapter parity, content invariants)
- `tests/test_dotgraph_integration.py` — 18 tests (probe matrix,
  emit_docs, doctor JSON/text, sync pre-step)

Full suite: 792 passed, 2 skipped.

## [0.5.2] — 2026-05-20

### Added — headless project onboarding

Three primitives gain `--from-stdin` + `--format json` so Coda (or any
orchestrator) can run the full project-setup ceremony without invoking
the interactive Q&A. The conversation lives in the orchestrator; dotagent
stays the data layer.

- **`dotagent project brief upload --from-stdin --force [--format json]`**
  — accepts the brief markdown body on stdin. Returns a parsed-counts
  receipt (`objectives`, `features`, `hard_rules`, `integrations`,
  `name`, `vision`) so the orchestrator can verify what landed.
- **`dotagent project init --from-stdin [--format json]`** — accepts a
  Project JSON payload (`name` required; `goal`, `description`,
  `success_criteria`, `stakeholders`, `constraints`, `out_of_scope`,
  `brief`, `brief_version`, `brief_objectives_covered`,
  `brief_features_covered`, `features_to_modules`, `tools` optional).
  Receipt confirms plan/scope paths.
- **`dotagent project add-module --from-stdin [--format json]`** —
  accepts a Module JSON payload (`name` required; `id`, `cross_module`,
  `implements_features`, `plan.{purpose,in_scope,out_of_scope,
  acceptance_criteria,dependencies,technical_approach,risks,
  estimated_effort}` optional). Receipt confirms id + acceptance count.

`--format json` mode also returns structured errors on misuse (missing
required field, invalid JSON, already-initialized) so orchestrators can
branch on them.

### Added — Coda onboarding prompt

- **`CODA_ONBOARDING_PROMPT.md`** — drop-in system prompt for the Coda
  agent that handles "start a new project." Drives the conversation
  through three phases (brief → project → module slate), calls the new
  primitives, validates with `dotagent project brief check` as the gate.
- Explicit fresh-project section: enumerates which files are EXPECTED
  to be absent on day zero (feature_master, FM-*.md, bug-registry,
  anti-patterns, architecture, db-impact-map, redis-key-registry, ops/*,
  source code) and reinforces that none of those are Coda's to create
  during onboarding — they come into existence inside dev cycles, by
  Claude, as work ships. The boundary holds even on day zero.
- `CODA_PROMPT.md` gains a "Headless project onboarding (0.5.2)" pointer
  in Section 8.5.

### Tests

+15 in `tests/test_headless_onboarding.py`:
- Brief upload from stdin (writes file · json receipt · refuses without
  force · rejects path+stdin · rejects neither)
- Project init from stdin (writes plan · requires name · invalid JSON
  · refuses when already initialized)
- Add-module from stdin (full payload · minimum payload · cross_module
  · requires name · explicit id override)
- End-to-end flow (brief → init → add-module, three receipts chain
  cleanly)

Full suite: **748 passed, 2 skipped.**

## [0.5.1] — 2026-05-20

### Changed
- Doc-only release. README.md fully rewritten for v0.5.0 (manifest as
  default, hand-maintained convention surfaced, doc-coverage CLI,
  derived-files orchestrator). USING_WITH_CLAUDE_CODE.md trimmed to a
  focused practical guide. CODA_PROMPT.md gains a Section 8.5 covering
  every v0.5 change (manifest default flip, hand-maintained docs,
  doc-coverage, derived files, service-repo inheritance, auto-regen,
  manifest preview CLI). CHANGELOG backfilled with entries for 0.4.7
  through 0.5.0.

### Removed
- `CLAUDE_MD_V2_PLAN.md`, `IMPLEMENTATION_PLAN.md`, `CODE_AUDIT_PLAN.md`,
  `PROJECT_CONTEXT.md` — all four were pre-implementation planning
  documents for features that have shipped. Removed to reduce drift
  surface. Plans live in git history if ever needed.

### Internal
- Two stale code-comment references to the removed planning docs
  updated to point at `docs/CLAUDE_MD_DESIGN.md` and inline language
  respectively.

## [0.5.0] — 2026-05-20

**The v3 navigation manifest is now the default render path.** Every feature
shipped in 0.4.7 → 0.4.13 was built on top of the manifest model; flipping
the default makes that contract official.

### Changed
- `DEFAULT_CONFIG["render"]["use_manifest"]`: `false` → `true`. New projects
  and existing projects without an explicit override pick up v3 on next
  `dotagent sync`. Opt-out: `render: { use_manifest: false }` in
  `.agent/config.yaml`. v1 renderer stays in the codebase as the safety
  net; malformed config falls back to v1.

### Tests
- `test_default_config_emits_v3_manifest` (new) — asserts the new default
  behaviour.
- `test_claude_adapter_uses_v1_when_flag_off` renamed to
  `..._when_flag_explicitly_off` to reflect the inverted default.
- `test_claude_adapter_renders_full_context_with_bug_registry` now
  explicitly sets v1 opt-out — it's testing v1's inline-content behaviour.

Full suite: **733 passed, 2 skipped.**

## [0.4.13] — 2026-05-20

### Changed
- Doc-only release. Trimmed `docs/` design references from 1718 lines →
  556 lines (68% reduction). Removed historical narrative (compendium →
  manifest rationale), token-economics prose, shipped roadmap items,
  glossaries that duplicated section content, and the
  `linkedin-followup-post.md` marketing file. Kept four-layer model,
  ownership rule, schema + coverage gates, tier model, how-to-extend,
  verbatim source spec (in `HAND_MAINTAINED_DOCS_CONVENTION.md`), and
  cross-doc navigation footers.

## [0.4.12] — 2026-05-20

### Added
- **`dotagent doc-coverage`** — read-only CLI returning the
  hand-maintained docs an agent should consider updating for a given
  changed-file set. Reads the `feature_master` structure; writes
  nothing. Designed for orchestrator gating (Coda doc-maintenance
  stage) and standalone git-hook / PR-review use.
- Severity model: 🔴 HARD (file is in an FM-###'s `## files` section) ·
  🟡 SUGGESTED (regex heuristics: db / redis / route / host paths) ·
  🟢 CHECK (always: anti-patterns + bug-registry on bug-fix commits).
- Flags: `--files` · `--format json|markdown|text` · `--commit-msg`
  (for `DA-BUG-LAYER-NNN` routing) · `--severity` filter · `--repo`.
- Tolerant Markdown parser (`src/dotagent/coverage.py::parse_fm_index`)
  supporting case variants on the `## files` heading, glob entries
  (`*` and `**`), and multi-FM claims of the same file.
- Hard non-write boundary enforced by
  `test_doc_coverage_never_writes_anything` — FS snapshot before/after.
- Reference: `docs/DOC_COVERAGE_CLI.md`.

### Tests
+29 in `tests/test_doc_coverage.py`.

## [0.4.11] — 2026-05-20

### Added
- **Hand-maintained docs convention registered as referenced sources.**
  dotagent now KNOWS about feature docs / deep dependency registries /
  ops references and surfaces them in CLAUDE.md without ever generating
  or overwriting them. Spec saved verbatim in
  `docs/HAND_MAINTAINED_DOCS_CONVENTION.md`.
- Two new categories: `CAT_FEATURE_DOCS` (📑) and `CAT_OPS` (🔧). Schema
  entries (`kind=KIND_FILE`, `required=False`, `HAND-MAINTAINED ·`
  prefix in `when_to_read`) added across project-root + single-repo
  tiers for: `feature_master.md` + templated
  `feature_master/FM-<id>-<slug>.md` · `db-impact-map-{master,tenant,vector}.md` ·
  `redis-key-registry-{tenant,global,events}.md` ·
  `bug-registry-{infrastructure,agents,orchestrator}.md` ·
  `ARCHITECTURE.md` · `ops/{service-registry,server-dependencies,tuning,tls-and-env}.md`.
- Manifest renderer's `_CATEGORY_PREFACE` dict — adds prefatory text
  for specific categories. `CAT_FEATURE_DOCS` carries the explicit
  "Entry point for any feature work: read `docs/feature_master.md`
  first, then the matching `docs/feature_master/FM-###-<slug>.md`..."
  guidance.
- `DEFAULT_CONFIG.sources.extra` registers all 15 hand-maintained paths
  with appropriate `kind` (bug_registry / db_impact_map / redis_keys /
  architecture / generic) so the indexer picks them up if they exist.

### Hard boundary
- All new paths declared `KIND_FILE`, never `KIND_GENERATED`.
- Test `test_regenerate_derived_files_never_writes_hand_maintained`
  writes sentinel content to every path, runs the full derived-files
  orchestrator, then asserts byte-for-byte unchanged. If you find a
  write path to one of these files, **that's a bug**.

### Tests
+67 in `tests/render/test_hand_maintained_docs.py`.

## [0.4.10] — 2026-05-20

### Added
- **Three new generators** in a unified orchestrator
  (`src/dotagent/render/derived.py::regenerate_derived_files()`):
  - **`docs/service-registry.md`** (project-root only) — per-repo
    table (id · path · default_branch · role · remote) generated from
    `.agent/git.yaml` `repos:` block. Replaces hand-written registries
    that drifted out of sync.
  - **`.agent/project/modules/<id>/HISTORY.md`** (per module) —
    cycle log, newest-first, with status badges: ✓ Passed QA · ✗
    Failed QA · ⏳ Contract frozen · ⏳ Dev handoff · 📝 Contract
    negotiation (round N/M) · 🟢 In progress.
  - **`.agent/dashboard.md`** (project tier) — single-page health
    snapshot with five sections: 📜 Open contracts · 🧪 Pending QA ·
    ⏰ Stalled (>14d) · 📅 Doc staleness (>60d) · 📡 Recent activity.
- Orchestrator called from `dotagent sync`, `dotagent project
  regenerate`, and the docs-change pre-commit hook. Fail-soft per
  generator (one failure never blocks the others). Safe to call from
  any state — silently no-ops when inputs are absent.
- Reference: `docs/DERIVED_FILES_DESIGN.md`.

### Tests
+32 across `tests/render/test_{service_registry,module_history,dashboard,derived_regen}.py`.

## [0.4.9] — 2026-05-20

### Changed
- **`../.agent/git.yaml` removed from service-repo schema.** `git.yaml`
  is project-root scope — it's the source of truth for the meta repo's
  branch rules, and service-repo devs never edit YAML. They read the
  rendered dashboard `../.agent/git.md` instead, which stays in
  MUST_READ. Regression test
  `test_git_yaml_is_project_root_only_not_service_repo` asserts the YAML
  stays out of the schema AND the rendered manifest.

### Added
- **Auto-regeneration of adapters on docs change.** When the pre-commit
  hook fires `dotagent observe pre-commit --files` and any staged file
  matches `docs/*.md`, every enabled adapter (CLAUDE.md, .cursorrules,
  copilot-instructions.md, AGENTS.md) is re-rendered alongside the
  source reindex. Regenerated files are NOT auto-staged. Opt-out:
  `hooks.auto_regen_on_docs: false` in `.agent/config.yaml`. Failures
  logged, never block the commit.

### Tests
+4 in `tests/test_observe_autoregen.py` + 1 new in
`test_service_repo_child.py`.

## [0.4.8] — 2026-05-20

### Added
- **Service-repo CLAUDE.md as child of project-root.**
  `_SERVICE_REPO_ENTRIES` gains 18 `../`-prefixed entries tagged
  `INHERITED ·` in their `when_to_read` text. Categories: MUST_READ
  (brief, rules, git.md), ARCHITECTURE (architecture, service-registry,
  shared-contracts, dependency-map), STYLE (style, patterns), CONFIG,
  PROJECT_PLAN (plan.yaml, SCOPE, CONTRACTS), PRIORITIES (contracts
  rollup), CONTRACTS (modules), BUGS, ANTI_PATTERNS.
- **Contract layer surfaced in service-repo schema.**
  `.agent/project/modules` + 7 cycle-artifact path patterns added under
  `CAT_CONTRACTS`. Inherited counterpart `../.agent/project/modules`
  added too — declares cross-service modules at the project-root tier.
- **`dotagent manifest` CLI** — explicit entrypoint for the v3
  renderer. Modes: stdout (default), `--write FILE`, `--diff FILE`
  (timestamp-normalized). Auto-detects tier or accepts `--tier`.
- **Dynamic `docs/` listing** in the rendered manifest
  (`_render_other_docs`) — auto-lists any `.md` files in `docs/` not
  covered by the canonical schema, with the file's first H1 as the
  description. Skips `docs/archive/`. Suppressed when empty.
- Reference: `docs/SERVICE_REPO_CLAUDE_MD.md`.

### Tests
+81 across `tests/render/test_{dynamic_docs,service_repo_child}.py` +
`tests/test_manifest_cmd.py`.

## [0.4.7] — 2026-05-20

### Added
- `.agent/project_brief.md` as optional `CAT_MUST_READ` entry in
  single-repo tier. End-to-end test revealed the gap — only `rules.md`
  appeared in MUST READ for single-repo until this PR.

## [0.4.6] — 2026-05-20

### Fixed
- **`replace_modules_section()` no longer duplicates the section** when
  a hand-written `## Modules & delivery status` heading exists without
  anchors. Now uses a sentinel-based strategy: strips every existing
  modules block (anchored OR plain-heading), replaces with a single
  fresh anchored block at the first removal site. Idempotent on
  repeated calls.
- **`render_modules_table()` Implements column now unions both sources**
  — reads from `module.implements_features` AND
  `plan.yaml::features_to_modules`. The audit's "Implements column
  empty" report is fixed.
- **`render_modules_table()` Owner column reads from
  `module.tools["_inline"]["owner"]`** (the layered-tier preservation
  stash from PR #29). Was always rendering `—` regardless of data.
- **`render_scope()` Description distinguished from Goal.** Previously
  both fell back to `brief.vision`, producing identical text. Now
  Description falls back to first 5 brief OBJs, then features, then
  vision as last resort. Goal stays as the one-line vision.
- **`dotagent project status` falls back to `brief.name`** when
  `plan.yaml::name` is empty. Defensive; only fires on absence.
- Tests: +12 in `test_regen_bug_fixes.py` covering all four failure
  modes from the user audit follow-up.

## [0.4.5] — 2026-05-20

### Added
- **`dotagent project regenerate`** — safe command to refresh all
  derived project files (`SCOPE.md`, `CONTRACTS.md`, brief Modules
  table) WITHOUT changing project state. Fills the gap noted in user
  audit: previously the only way to refresh `SCOPE.md` was a project
  state change (add-module / start / etc.). Supports `--dry-run`.

### Fixed
- **`render_scope()` falls back to brief data** when plan.yaml lacks
  top-level `name` / `goal` / `description` / `out_of_scope` /
  `success_criteria` (common in layered-tier plan.yaml). Previously a
  regenerate would HOLLOW the file because render_scope read only from
  project fields. Now falls back to brief.name / brief.vision /
  brief.non_goals / brief.success_metrics. If both are absent, writes
  `(unset — add X)` markers instead of empty content.
- **Traceability audit unions both FEAT sources.**
  `audit_feat_to_module` now accepts both `module.yaml::implements_features`
  AND `plan.yaml::features_to_modules`. Previously it only read the
  per-module field, so layered-tier plan.yaml shapes where the mapping
  lives only at the project level reported every FEAT as unmapped.
- **Frozen contracts get info, not fail, for missing FEAT-NN.**
  `ContractRef.is_frozen` flag downgrades the
  `contract-no-feat` finding to `frozen-contract-no-feat` info. Frozen
  contracts are immutable historical artifacts; demanding edits to
  restore traceability is the wrong shape. Live contracts still fail
  loud.
- Tests: +12 in `tests/project/test_aigent_audit_scenario.py` end-to-end
  covering the exact failure modes from the user audit.

## [0.4.4] — 2026-05-20

### Fixed
- **Brief OBJ parser** now tolerates titles inside the bold span:
  `**OBJ-01 · Universal AI chat layer**: description` parses as
  id=OBJ-01 with text combining the title + description (previously
  parsed zero IDs because the regex required the bold to contain only
  the ID).
- **H2 section matching** is now case-insensitive and tolerant of
  trailing parentheticals + synonyms:
  - `Business objectives` ↔ `Objectives` ↔ `business objectives`
  - `Features` ↔ `Capabilities` ↔ `Features (capabilities)`
  - `Target users` ↔ `Personas` ↔ `Users`
  - `Hard rules` ↔ `Rules`
  - `External integrations` ↔ `Integrations`
  - and more — see the `_section()` resolver in `brief.py::parse()`.
- **`SCOPE.md` banner restored.** `render_scope()` now emits the
  `<!-- generated by dotagent -->` banner so `dotagent structure check`
  stops flagging it as a "hand-edited generated file."
- Tests: +9 in `tests/project/test_brief_aigent_shape.py`.

## [0.4.3] — 2026-05-20

### Fixed
- `contracts_rollup.RepoSummary` now distinguishes informational notes
  from real errors via `note: str` + `is_error: bool` (the old `error`
  field stays as a backward-compat alias that only fires on real errors).
- Service repos that exist but don't run their own per-repo cycle no
  longer render as `_error: no plan.yaml in repo_`. They render as
  `_no cycles tracked here — meta tier owns project state_` — info,
  not error. Valid topology for projects that keep all cycle state at
  the meta tier (e.g. Aigent).
- Repos missing `.agent/` entirely render as info `_no dotagent install
  in this service repo_` instead of error.
- Manifest entries pointing at non-existent paths still render as real
  errors with a `⚠ error:` glyph so users can tell the difference at a glance.
- Tests: +4 in `test_contracts_rollup.py` covering info/error distinction.

## [0.4.2] — 2026-05-20

### Fixed
- `Project.from_dict()` now reads the layered-tier inline `modules:`
  block (both dict-keyed-by-id and list-with-id shapes). Previously
  the contracts loader ignored it, producing empty dashboards even
  when the plan.yaml had every module populated.
- `Project.to_dict()` round-trips the inline modules block so
  `save_project()` no longer silently drops layered-tier data.
- Non-Module fields (`repo`, `owner`, `deps`, `integrations`) in inline
  records are stashed into `module.tools["_inline"]` so they survive
  the round-trip without needing to be first-class on the dataclass.
- `contracts_rollup` now accepts `alias:` or `name:` as fallbacks for
  the `id:` key in `repos[]` entries (a shape Coda-generated plan.yaml
  files have used).
- Tests: 10 new in `tests/project/test_layered_plan_schema.py`.

## [0.4.1] — 2026-05-20

### Fixed
- `Project.from_dict()` and `Module.from_dict()` no longer KeyError on
  plan.yaml / module.yaml files that omit the top-level `name:` key.
  This shape occurs in the new layered-tier plan.yaml (which can lead
  with `brief_features_covered`, `features_to_modules`, `modules`, `repos`)
  and previously crashed `dotagent project contracts rebuild` and any
  other command that loaded the project model. Tolerant defaults:
  `Project.name → ""`, `Module.name → module.id || ""`.
  Regression covered by 7 new tests in `tests/project/test_loader_tolerance.py`.

## [0.4.0] — 2026-05-20

Implementation of the **layered project architecture** plan
(see `IMPLEMENTATION_PLAN.md`). 14 PRs shipped together in this release.
Net **+208 tests** (230 → 438 passing).

### Added — Phase 0: Foundation (PRs #1–#2)
- **Canonical structure schema** (`canonical_structure.py`): data-driven
  declaration of what each tier (project-root / service-repo / single-repo)
  must contain. `dotagent structure show / check / version`.
- **`dotagent migrate`**: schema-version upgrades with 5-mode detection
  (FRESH, MID_PROJECT, PRE_V0_4, UPGRADE, CURRENT), `--plan` preview, and
  fully reversible `--rollback` via `.agent/.migration-log.md`.
- Doctor extended to surface structure deviations + pending archive count
  + bug-prefix declaration.

### Added — Phase 1: Document lifecycle (PRs #3–#4)
- **`dotagent archive`**: scan/run/restore/list. Triggers per source:
  bug-registry entries with `status: fixed` + ≥30 days; anti-patterns with
  `rescinded: true`; shipped modules ≥90 days. Year-stamped archives at
  `docs/archive/YYYY/`. Every move logged and reversible.
- **Tiered bug registry**: `bugs.id_prefix:` in config (e.g. `BE`, `AGT`,
  `PORTAL`). Cross-references between repos detected automatically and
  surfaced in CLAUDE.md.

### Added — Phase 2: Brief + traceability (PRs #5–#7)
- **`project_brief.md`** — durable business intent. Hand-written or AI-drafted
  on init. Locked template includes Vision, Personas, OBJ-NN, FEAT-NN
  (with **Serves:** + behavior bullets), RULE-NN, Glossary, Tenancy,
  Non-goals, Integrations.
- **`dotagent project brief init / upload / show / edit / check`**.
- **Traceability**: `Module.implements_features: [FEAT-NN]`, `Project.brief_*`
  fields, `project/traceability.py` audits OBJ→FEAT→Module→Contract chain.
- **Contract template** gets `<!-- anchor: business-traceability -->`
  section; validate refuses without FEAT citation.
- **Rubric signal S11** — Business traceability (0-3). Total max **30 → 33**.
  Bands: ready ≥30, polish ≥24, rework ≥18, not_ready ≤17.
- **CLAUDE.md** renders the structured subset (OBJs, this-repo's FEATs,
  hard rules, glossary, tenancy, non-goals, integrations) in a "Project
  context" section.

### Added — Phase 3: Contract discoverability (PR #8)
- **Per-repo `.agent/project/CONTRACTS.md`** — module-grouped dashboard
  with markdown links to every cycle. Auto-regenerated on every contract
  op (`init_contract`, `advance_round`, `freeze_contract`, `add_module`).
- `dotagent project contracts show / rebuild` with `--format`,
  `--open`, `--frozen`, `--module` filters.

### Added — Phase 4: Plan negotiation + brief modules table (PRs #9–#10)
- **Plan negotiation primitives** — pure data layer mirroring contract
  negotiation. `dotagent project plan write-draft / write-review / show /
  diff / converged / freeze / log`. `--actor` is opaque (no internal
  Planner/QA concept); content-hash convergence detection; YAML
  validated on every write. **No LLM inside dotagent.**
- **Auto-generated Modules table** inside `project_brief.md` between
  `<!-- anchor: modules-table-begin/end -->` anchors. Hand-written content
  outside the anchors preserved. Regenerated on every project event.

### Added — Phase 5: Layered structure (PRs #11–#12)
- **`parent:` field** in `.agent/config.yaml` — service repos inherit
  cross-cutting `.agent/*.md` content from a project-root layer. Chain
  walks up to 3 levels with cycle detection. Brief inherits via the
  same chain when local is absent. Memory layers stay service-local
  by design.
- **Cross-repo rollup**: `Project Root/contracts.md` (lowercase, per
  convention) aggregates contracts state from every entry in
  `Project.repos[]`. `dotagent project contracts rollup` and
  `rebuild --all-repos`.

### Added — Phase 6: Git layout + enforcement (PRs #13–#14)
- **`.agent/git.yaml`** — declarative meta-repo + service-repo manifest
  with branch rules per remote.
- **`dotagent git`** subgroup: `init / rebuild / status / push / pull /
  clone-services / verify / init-hooks / scaffold-protection`.
- **Branch reservation enforcement** — pre-push hook (`init-hooks`)
  refuses code files on the meta branch; GitHub Actions workflow
  (`scaffold-protection`) enforces server-side. Validation that meta
  branch is never `main` when `main_branch_policy: locked`.
- **Critical scope**: enforcement applies ONLY to the meta repo. Service
  repos' `main` is unrestricted.

### Architectural commitments held
- dotagent is the **data layer**. No LLM invocation inside; orchestrators
  (Coda, scripts, humans) drive negotiation loops via `--actor` and
  `--rationale` flags.
- `main` locked **only on meta repo** (`strategy: dedicated_repo`,
  `main_branch_policy: locked`). Service repos unchanged.
- Single-repo dotagent users **unaffected** — every PR additive,
  backward-compatible.
- All 230 pre-existing tests still pass (the only updates: rubric signal
  count + band thresholds for the S11 addition).

## [0.3.0] — 2026-05-16

Two governance features shipped in response to LinkedIn feedback from
Faisal Feroz on the four-memory article: "how do you handle conflicts
when working memory contradicts what semantic memory says is the team
standard" and "I would push you to also think about expiration and review
cycles for those entries because team knowledge decays as the codebase
evolves."

### Added — Conflict Detection (Module 1)
- `Context.detect_conflicts()` compares the active actor's
  `current.recent_files` against bug-registry / anti-pattern entries
  citing those files; returns severity-ranked rows.
- New `⚠ Rule conflicts in active edits` section in every adapter output
  (CLAUDE.md / .cursorrules / .github/copilot-instructions.md / AGENTS.md).
  Suppressed when no conflicts exist — no noise.
- Section placement: immediately after the Project section and *before*
  the Rules section, so the warning is impossible to miss.
- `context.conflicts_top_n` config knob (default 8).

### Added — Rule Lifecycle (Module 2)
- `SemanticEntry` gains `graduated_at`, `review_after`, `last_reviewed_at`,
  `expired_at` fields. Persisted via a `<!-- dotagent-meta: -->` HTML
  comment for clean round-trip without YAML frontmatter clutter.
- Default rule lifetime: 180 days. Set explicitly via
  `SemanticMemory.write(entry, lifetime_days=N)`.
- `dotagent dream review-stale` lists rules that are overdue, due soon,
  or whose cited files have churned since graduation.
- `dotagent dream rerationale <rule-id> --rationale "..."` extends
  `review_after`. Rationale is mandatory (`ValueError` on empty).
- `dotagent dream expire-stale [--grace-period-days 30] [--dry-run]`
  moves past-grace rules to `.agent/dream/expired/` (never deletes).
  Expired rules carry an `expired_at` stamp and revival instructions.
- New `⚠ Rule lifecycle` section in CLAUDE.md surfaces a count of
  overdue / due-soon rules. Suppressed when none exist.
- Backward compatibility: pre-Module-2 rules without metadata are
  bucketed as legacy and treated as stale if their file mtime exceeds
  the default lifetime.

### Fixed
- `SemanticMemory.read()` no longer nests rendered output back into
  `entry.body`. Previously, a re-rationale cycle would carry the prior
  rendered template (including stale meta comment) into the next write,
  producing duplicated sections and incorrect lifecycle round-trips.
- `_parse_meta()` now returns the LAST meta comment in a rule file, so
  a re-rationale's updated metadata wins over earlier writes.
- `lifecycle._aware()` normalizes parsed datetimes to UTC so date math
  with `datetime.now(timezone.utc)` no longer raises on naive values.

### Tests
- 137/137 passing (113 baseline + 11 conflict + 13 lifecycle).
- Coverage includes: defaults, custom lifetime, caller-supplied dates,
  legacy round-trip, fresh / overdue / due-soon / cited-files-churned
  buckets, rerationale rationale enforcement, extension semantics,
  expire-stale move + dry-run + grace period, render-body surface +
  suppression for both features.

## [0.2.0] — 2026-05-06

First launch-ready release. Brings the walking-skeleton from 0.1.0 to a usable
end-to-end system: every memory, every adapter, every visibility command,
auto-dream graduation with mandatory rationale, the four built-in tools, the
skills runtime, the centralized server, and the Cursor + Copilot bridges.

### Added — context & memory
- `docs/` is wired as the canonical source of truth via `.agent/config.yaml`
  `sources:` block. Six built-in source kinds (bug-registry, anti-patterns,
  redis-keys, db-impact-map, dependency-map, architecture) with tolerant
  markdown parsers; arbitrary extras via `sources.extra`.
- Pointer cards committed at `.agent/memory/semantic/sources/<id>.md`;
  structured cache (gitignored) at `.agent/.cache/sources.json`.
- Unified `dotagent.context.build()` resolver merges five `.agent/*.md` files +
  indexed sources + semantic memory + personal memory + working memory + recent
  episodic events into one `Context` object.
- Per-actor working-memory `current.json` tracks branch / recent files /
  recent events / current task. Updated by every observed event.
- `dotagent.ingest` parses existing `CLAUDE.md` / `.cursorrules` /
  `.github/copilot-instructions.md` / `AGENTS.md` and routes H2 sections into
  the matching `.agent/*.md` bucket on init (hand-written copy survives).

### Added — adapters
- All four adapters (Claude Code, Cursor, Copilot, OpenCode) render the full
  `Context`: project rules, ranked bug registry, anti-patterns, DB hotspots,
  redis keys, dependency map, architecture pointers, personal preferences for
  the active actor, working-memory snapshot, recent activity, and a source-of-
  truth footer.
- `CustomAdapter` renders Jinja templates from
  `.agent/adapters/custom/templates/*.j2` with `{# output: <path> #}`
  directives.

### Added — visibility (Phase 2)
- SQLite event index auto-built from episodic JSONL.
- Commands: `who --file/--rule`, `activity`, `timeline`, `feed`,
  `leaderboard`, `reindex-events`.
- `prepare-commit-msg` hook + `dotagent trailer` add a `Co-authored-by:
  dotagent ... actor=X tool=Y` trailer so attribution survives in `git log`.

### Added — skills (Phase 3)
- Skill loader parses YAML frontmatter + body from `.agent/skills/*.md`.
- Commands: `skill list/show/run/pipeline`. LLM-backed via `anthropic`;
  without API key returns the resolved prompt for inspection.

### Added — tools (Phase 4)
- `tool pattern-extractor` — Python AST + JS/TS regex import scan, emits
  `SemanticEntry` records.
- `tool memory <query>` — search across all four memory stores; `--summary`
  for store-level counts.
- `tool debug <stack>` — match a stack trace against episodic memory +
  bug registry.
- `tool checklist --since` — synthesize a pre-deploy gate from rules.md +
  bug-registry + recent reverts/fixes.

### Added — auto-dream (Phase 5)
- Heuristic signal extraction (revert clusters, repeat-fix, frequent-failure,
  cross-actor anti-pattern).
- Embedding-based clusters via sentence-transformers + sklearn DBSCAN (opt-in
  via `pip install 'dotagent[ml]'`).
- `dream run / list / graduate / reject` — graduate/reject require a
  non-empty rationale (raises `ValueError` otherwise). Graduations flow into
  semantic memory as `auto-dream` rules.
- `dream cron-install / cron-uninstall`, `dream github-action` writes a
  workflow template.

### Added — polish (Phase 6)
- `sync --dry-run` shows unified diff vs on-disk files.
- `migrate-cco` — lossless Claude-Code-Optimization migrator: references
  docs/ as sources (no copy), imports `prompts/*.md` as
  `.agent/skills/imported-<slug>.md`, ingests existing CLAUDE.md.

### Added — Phase 7 closeout
- **Cursor < 0.40 file-watcher fallback.** `dotagent watch cursor` debounces
  file events (2s window), gates on a running Cursor process, forwards as
  `tool=cursor`. Requires `pip install 'dotagent[watch]'`.
- **dotagent server.** FastAPI app with token RBAC (admin/writer/reader),
  `POST /events`, `GET /events`, SSE stream, token management, live
  dashboard. SQLite persistence. `dotagent serve --host/--port`. Requires
  `pip install 'dotagent[server]'`. Clients forward via
  `.agent/config.yaml` `server.url/token/forward_events`.
- **VS Code Copilot extension scaffold** at `extensions/vscode-copilot/`.
  Listens for inline-suggest commands; saves/edits inside a timing window
  forward to `dotagent observe ... --tool copilot`.

### Added — operations
- `dotagent doctor` — self-check for common misconfigurations.
- `DOTAGENT_DEBUG=1` enables debug logging (silent `except` paths now log).
- GitHub Actions CI: `tests` on push/PR across Python 3.11 + 3.12.
- `examples/` folder with a sample project showing the expected `docs/*.md`
  format.

### pyproject extras
- `[ml]` — sentence-transformers + scikit-learn for embedding clusters.
- `[server]` — fastapi + uvicorn + starlette.
- `[watch]` — watchdog (Cursor file-watcher).
- `[all]` — all three above.
- `[dev]` — pytest + ruff for contributors.

### Tests
- 60 → 65+ passing (Phase 7 closeout + doctor coverage).

## [0.1.0] — 2026-05-05

Initial walking-skeleton release. Zero-prompt `dotagent init`, idempotent
`sync`, four adapters (claude / cursor / copilot / opencode), identity model,
git + Claude Code hooks, four-memory scaffolding, full test suite (13 tests).
The package is plug-and-play but `docs/` is not yet wired as the source of
truth — that came in 0.2.0.
