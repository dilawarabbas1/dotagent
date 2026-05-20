# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic](https://semver.org/spec/v2.0.0.html).

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
