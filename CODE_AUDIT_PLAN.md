# Implementation Plan — Code-aware Document Audit (v0.5.0)

_Drafted: 2026-05-20  ·  Target: `dotagent` v0.5.0  ·  Estimated calendar: 4–6 weeks_

---

## Executive summary

Today dotagent reads `docs/*.md` and `.agent/*.md` and grades them on
structural quality (sections present, IDs valid, traceability intact).
It **cannot tell if those docs match the actual code**. The Aigent
project audit exposed exactly this gap: `architecture.md` claims 22 task
agents, `dependency-map.md` says 23, `.agent/architecture.md` says 28.
None of dotagent's existing audits can adjudicate.

This plan adds **code-aware crosschecks** so the audit chain can verify
doc claims against real code, not just other docs.

The deliverable: an end-to-end `dotagent code audit` command that crawls
the codebase, extracts machine-checkable claims from `docs/*.md` and
`.agent/*.md`, compares them, and reports drift with severity bands.

---

## Problem statement

Three concrete cases from the Aigent audit, all unsolvable today:

1. **Agent count drift** — three docs report different totals (22 / 23 /
   28). dotagent can't know which is right because it doesn't count
   files in the codebase.

2. **Redis-keys vs production usage** — `docs/redis-keys.md` documents
   9 key namespaces. Is the code actually using only those 9? Are there
   undocumented keys? dotagent has no way to grep.

3. **DB-impact-map vs migrations** — `docs/db-impact-map.md` lists 8
   tables flagged HIGH/VERY HIGH risk. Are those still the active
   tables? Have new tables appeared in migrations since the map was
   last edited? dotagent can't read migrations.

Cross-cutting impact: every contract the dev/QA loop produces inherits
the doc accuracy. If `architecture.md` is wrong, every contract that
cites it is wrong. The leverage is high.

---

## Goals

1. **Code crawler** — walks the codebase, builds a machine-readable
   index of routes, classes, functions, imports, decorators, SQL/ORM
   models, Redis usage patterns, agent files.

2. **Doc-claim extractor** — parses `docs/*.md` and `.agent/*.md` for
   machine-checkable claims: counts, lists of identifiers, file
   references, key patterns.

3. **Crosschecks** — per source kind (architecture, redis-keys,
   db-impact-map, dependency-map, bug-registry, agents), report
   doc-vs-code drift with severity bands.

4. **`dotagent code audit`** — umbrella command. Same UX as
   `dotagent project brief check`: text or JSON output, exit codes for
   CI gating, optional `--write` for safe auto-fixes.

5. **Doctor integration** — drift count surfaces in `dotagent doctor`
   so it's visible alongside structure + archive + brief audits.

6. **Configuration** — `.agent/config.yaml::code` block declares scan
   roots, excludes, and per-language settings.

## Non-goals

- **LLM-driven semantic judgment** ("does this prose accurately describe
  the architecture?") — out of scope. Coda handles that side via the
  existing audit prompt.
- **Code mutation** — dotagent reads code, never writes it. `--write`
  on the audit command only fixes count corrections in docs.
- **Multi-language polyglot crawl at launch.** Python first; TypeScript
  in a follow-up PR; other languages later if demand surfaces.
- **Live reconciliation with running infrastructure.** No connection to
  Redis / Postgres / k8s. Static analysis only.
- **Performance optimization for monorepos > 100k files.** v1 targets
  projects up to 10k files; bigger repos may need follow-up indexing.

---

## Locked design decisions (D1–D10)

These are **closed**. Re-opening any of them invalidates dependent PRs.

| # | Decision | Rationale |
|---|---|---|
| D1 | dotagent stays read-only on code. Never modifies source files. | Boundary preservation; same principle as Coda decoupling. |
| D2 | Python first; TypeScript second. Languages added one PR at a time. | Pragmatic scope. Most dotagent users have Python backends. |
| D3 | Code index lives at `.agent/.cache/code_index.json`. Regenerated on `dotagent code scan`; not committed. | Same pattern as `.agent/.cache/sources.json`. |
| D4 | One crosscheck module per source kind (routes, redis, db, bugs, agents). | Each crosscheck owns its parse-and-compare logic; loose coupling. |
| D5 | All crosschecks return the same `Drift` dataclass (severity, code, message, fix, evidence). | Uniform reporting; same shape as existing `Finding` dataclass. |
| D6 | `--write` only auto-fixes **counts in docs** (e.g. "22 agents" → "23 agents"). Never adds/removes list entries; never touches code. | Auto-fix safety. Count corrections are unambiguous; list edits aren't. |
| D7 | Crosschecks are **opt-in per source** via `.agent/config.yaml::code.crosschecks`. Default: all enabled. | Some projects (e.g. polyglot) may want to disable specific crosschecks. |
| D8 | Doc-claim extraction is regex-based, not LLM. Misses edge cases by design. | Determinism + speed. LLM extraction is Coda's job. |
| D9 | `dotagent code audit` exit codes: 0 = clean, 1 = at least one fail, 2 = at least one warn (no fails). | Same convention as other audits; CI-friendly. |
| D10 | `code_index.json` schema versioned via `schema_version: int` field. Bumped on breaking changes. | Stable contract for `--format json` consumers. |

---

## Affected user surfaces

| Surface | Change |
|---|---|
| `dotagent code` | **NEW command group** with `scan`, `audit`, `crosscheck <kind>`, `show` |
| `dotagent doctor` | New check: `_check_code_drift()` — info-level if crosschecks haven't run; warn if `< 7 days` of pending drift |
| `.agent/config.yaml` | New `code:` block with scan settings |
| `.agent/.cache/code_index.json` | New cache file (gitignored) |
| `CLAUDE.md` rendering | New "Code reality" section showing drift counts (suppressed if clean) |
| `dotagent structure check` | Doesn't change |
| Project / brief / contract commands | Don't change |

---

## The 8 PRs across 3 phases

```
Phase 1 — Foundation (BLOCKING)
  PR #1 · Code crawler core (file walk, AST index, cache)
  PR #2 · `dotagent code audit` umbrella + Drift dataclass + reporting

Phase 2 — Crosschecks (one per source kind; each ships value standalone)
  PR #3 · Counts crosscheck (agents, modules, services — number drift)
  PR #4 · Routes crosscheck (FastAPI/Flask routes vs architecture.md)
  PR #5 · Redis crosscheck (key patterns in code vs redis-keys.md)
  PR #6 · Database crosscheck (models/migrations vs db-impact-map.md)
  PR #7 · Bug-ref crosscheck (bug-ID refs in code vs bug-registry.md)

Phase 3 — Polish
  PR #8 · doctor integration + `--write` auto-fix + TypeScript crawler
```

### Dependency graph

```
PR #1 (crawler) ──► PR #2 (audit umbrella)
                ──► PR #3, #4, #5, #6, #7 (crosschecks — parallel)
                                            ──► PR #8 (polish)
```

PRs #3–#7 are independent and can ship in any order once #1 + #2 are in.

---

## PR-by-PR full specification

### PR #1 — Code crawler core

**Goal:** walks the repo, builds `.agent/.cache/code_index.json`. Pure
read; no LLM. Python AST as the v1 language; TypeScript deferred to #8.

**Files to create**

| Path | Purpose |
|---|---|
| `src/dotagent/code/__init__.py` | Public surface: `scan()`, `load_index()` |
| `src/dotagent/code/crawler.py` | File walk + per-language dispatcher |
| `src/dotagent/code/python_walker.py` | AST walk: classes, functions, decorators, imports, route registrations |
| `src/dotagent/code/index.py` | `CodeIndex` dataclass + JSON serialization with `schema_version` |
| `src/dotagent/code/config.py` | Read `.agent/config.yaml::code` for scan roots / excludes |
| `tests/code/test_crawler.py` | 8 tests |
| `tests/code/test_python_walker.py` | 12 tests |
| `tests/code/test_index_serialization.py` | 5 tests |

**Public API**

```python
from dotagent.code import scan, load_index

# Walks the repo per config; writes .agent/.cache/code_index.json
index = scan(paths, force=False)

# Loads the cached index (or returns None if missing/stale)
index = load_index(paths)
```

**`CodeIndex` shape (v1)**

```python
@dataclass
class CodeIndex:
    schema_version: int = 1
    repo_path: str
    generated_at: str
    languages: list[str]                  # ["python"] in v1
    files: list[FileEntry]                # one per scanned file
    routes: list[RouteEntry]              # extracted route registrations
    classes: list[ClassEntry]
    functions: list[FunctionEntry]
    imports: dict[str, list[str]]         # file → [imported modules]
    decorators_seen: dict[str, int]       # @app.get, @app.post, etc. → count
```

**Scan config** (in `.agent/config.yaml`)

```yaml
code:
  enabled: true
  scan_roots: ["src/", "app/", "backend/"]
  excludes: ["**/__pycache__", "**/.venv", "**/node_modules"]
  languages: ["python"]
```

**Tests** (25 total)

- Walks a tmp_path with mixed files; correctly excludes ignored dirs
- Python file with `@app.get("/x")` produces a route entry
- Class with no decorators produces a class entry
- Functions inside classes attributed to class
- Re-scan picks up new files
- Stale cache detection (mtime check) triggers re-scan
- Force flag bypasses cache
- Empty repo returns empty index, no crash
- Invalid Python file logged + skipped (doesn't crash the scan)
- Index serializes to JSON; round-trip stable
- Schema version increments on breaking changes (test asserts >= 1)
- ... + 14 more covering edge cases

**Effort:** ~1,000 lines
**Risk:** medium — AST parsing has edge cases; needs broad test coverage
**Acceptance:** scanning Aigent backend produces an index with route + class entries; cache hit on second run

---

### PR #2 — `dotagent code audit` umbrella + Drift dataclass

**Goal:** the umbrella command that runs all enabled crosschecks and
produces a unified report. Crosschecks themselves are stubs in this PR;
PRs #3–#7 fill them in.

**Files to create**

| Path | Purpose |
|---|---|
| `src/dotagent/code/audit.py` | Orchestrator: loads index + runs crosschecks + aggregates results |
| `src/dotagent/code/drift.py` | `Drift` dataclass + reporting helpers |
| `src/dotagent/code/crosschecks/__init__.py` | Registry of available crosschecks |
| `src/dotagent/code/crosschecks/base.py` | Abstract base class for crosschecks |
| `src/dotagent/commands/code_cmd.py` | `dotagent code` command group: `scan`, `audit`, `crosscheck`, `show` |
| `tests/code/test_audit.py` | 8 tests |

**CLI surface**

```bash
dotagent code scan                       # walk + index; writes cache
dotagent code scan --force               # rebuild even if cache exists
dotagent code audit                      # run every enabled crosscheck
dotagent code audit --format json        # machine-readable
dotagent code audit --min-severity warn  # CI gate
dotagent code audit --write              # auto-fix safe drift (PR #8)
dotagent code crosscheck routes          # run one named crosscheck
dotagent code crosscheck redis --json    # JSON for a single check
dotagent code show                       # print loaded index summary
```

**`Drift` dataclass**

```python
@dataclass
class Drift:
    crosscheck: str                # "routes", "redis", "db", etc.
    severity: str                  # fail | warn | info
    code: str                      # e.g. "agent-count-drift"
    message: str
    fix: str = ""                  # human-readable remediation
    auto_fixable: bool = False     # PR #8 uses this
    evidence: dict = field(default_factory=dict)
                                    # {"doc_value": 22, "code_value": 23, ...}
```

**Audit output (text)**

```
code audit — Aigent
  index: 2026-05-20T10:23:00Z · 1,247 files · python
  crosschecks enabled: counts · routes · redis · db · bugs

  [✗] counts/agent-count-drift
        docs/architecture.md says 22 agents; code has 23
        evidence: doc=22, code=23, files in src/backend/dotagent_agents/=23
        fix: update agent count in docs/architecture.md §2a (line 53)

  [!] redis/undocumented-key
        code uses `cache:user:*` but docs/redis-keys.md doesn't list it
        evidence: file=src/backend/cache.py:42

  [i] bugs/code-ref-no-registry-entry
        code references `BE-0413` (in src/backend/auth.py:117) but
        docs/bug-registry.md has no entry
        evidence: file=src/backend/auth.py:117

summary: 1 fail · 1 warn · 1 info
```

**Tests** (8)

- Empty repo + no crosschecks → exit 0, "clean" output
- One crosscheck reports fail → exit 1
- One crosscheck reports warn only → exit 2 (with `--min-severity warn`)
- One info finding → exit 0 (info isn't a gate)
- `--format json` produces stable shape
- Crosscheck filter: `crosscheck routes` runs only that one
- `code show` prints index counts
- Crosschecks disabled in config → not run

**Effort:** ~600 lines
**Risk:** low — orchestration over the abstract crosscheck base
**Acceptance:** `dotagent code audit` runs without errors and reports
"no crosschecks enabled yet" until PRs #3–#7 land

---

### PR #3 — Counts crosscheck

**Goal:** the simplest crosscheck. Compares numeric claims in docs
("22 agents", "8 services", "3 shards") against file counts in the
code index.

**Why it ships first:** highest-value-per-line. The Aigent audit's #1
finding was the agent-count drift. This crosscheck catches that
immediately.

**Files to create**

| Path | Purpose |
|---|---|
| `src/dotagent/code/crosschecks/counts.py` | The crosscheck implementation |
| `src/dotagent/code/extractors/count_claims.py` | Regex extraction of count claims from docs |
| `tests/code/test_counts_crosscheck.py` | 10 tests |

**Claim extraction patterns**

Looks for patterns like:
- `22 agents`, `22 task agents`, `22 task-agents`
- `8 services`, `8 microservices`
- `3 shards`, `3-shard`, `three-shard`
- `45 routes`, `45 endpoints`

Each claim is anchored to a (file, line, kind, value).

**Code reality counters**

- agents: count files matching `**/agents/*.py` or `**/agent_*.py` (configurable)
- services: count directories at scan-root depth (configurable)
- routes: count entries in `code_index.routes`
- shards: parse from migration filenames or `schema.py` (configurable)

**Configurable mappings**

```yaml
code:
  count_mappings:
    agents:
      glob: "**/agents/*.py"
      exclude: ["**/test_*.py", "**/__init__.py"]
    services:
      glob: "services/*/"
      kind: "dir"
```

**Tests** (10)

- Doc says "22 agents", code has 23 files → fail with auto_fixable=True
- Doc says "22 agents", code has 22 → no finding
- Doc has no count claim → no finding
- Count claim with synonyms ("task-agent" vs "agent") matches
- Multiple docs disagree about the same count → all flagged
- `--write` updates the doc number (PR #8)
- Configurable globs work
- Word-number "twenty-two" → matched and compared

**Effort:** ~400 lines
**Risk:** low — bounded scope
**Acceptance:** running on a known-drift case produces a clear fix suggestion

---

### PR #4 — Routes crosscheck

**Goal:** compares route declarations in code (FastAPI, Flask, Django,
Express patterns) against route lists in `docs/architecture.md` and
`docs/api-routes.md` (if present).

**Files**

| Path | Purpose |
|---|---|
| `src/dotagent/code/crosschecks/routes.py` | Route compare logic |
| `src/dotagent/code/extractors/route_claims.py` | Parses route tables/lists from docs |
| `tests/code/test_routes_crosscheck.py` | 12 tests |

**Detection**

Code-side: already in `code_index.routes` (from PR #1's `python_walker`)
- `@app.get("/path")` → route entry
- `@router.post("/path")` → route entry
- `app.add_route("/path", handler)` → route entry

Doc-side: extract route tables (markdown tables with method/path
columns) or bulleted lists of "POST /x, GET /y".

**Drift categories**

- `route-in-code-not-doc` — code has it, docs don't (warn)
- `route-in-doc-not-code` — docs claim it, code doesn't (fail; missing implementation)
- `route-method-mismatch` — same path, different HTTP methods declared (warn)

**Effort:** ~500 lines
**Risk:** medium — route extraction has framework-specific quirks
**Acceptance:** Aigent backend's actual routes match against docs/architecture.md §API; any mismatch is reported

---

### PR #5 — Redis crosscheck

**Goal:** ensures `docs/redis-keys.md` matches actual Redis usage in
code.

**Files**

| Path | Purpose |
|---|---|
| `src/dotagent/code/crosschecks/redis.py` | Compare logic |
| `src/dotagent/code/extractors/redis_keys.py` | Grep code for Redis key patterns |
| `tests/code/test_redis_crosscheck.py` | 10 tests |

**Detection**

Code-side: regex grep for Redis client calls:
- `redis.set("key:...")`
- `redis.get(f"prefix:{x}")`
- `r.hset(...)` etc.

Extract the literal/f-string key pattern → key-namespace fingerprint.

Doc-side: parse `docs/redis-keys.md` H2 entries (each is a key
namespace).

**Drift categories**

- `redis-namespace-in-code-not-doc` (warn)
- `redis-namespace-in-doc-not-code` (info — could be planned)
- `redis-namespace-mismatch-ttl` (when both doc and code mention TTL but differ)

**Effort:** ~450 lines
**Risk:** medium — Redis usage patterns vary widely
**Acceptance:** all 9 of Aigent's documented namespaces match grep'd
keys in code; any undocumented key flagged

---

### PR #6 — Database crosscheck

**Goal:** ensures `docs/db-impact-map.md` matches actual ORM models +
migrations.

**Files**

| Path | Purpose |
|---|---|
| `src/dotagent/code/crosschecks/database.py` | Compare logic |
| `src/dotagent/code/extractors/db_models.py` | Parse SQLAlchemy / Django models + Alembic migrations |
| `tests/code/test_db_crosscheck.py` | 12 tests |

**Detection**

Code-side:
- SQLAlchemy: `class Foo(Base): __tablename__ = "foos"`
- Django: `class Foo(models.Model)` with Meta → table
- Migrations: parse `alembic/versions/*.py` for `op.create_table()`,
  `op.add_column()`

Doc-side: parse `docs/db-impact-map.md` table list.

**Drift categories**

- `table-in-code-not-doc` (warn)
- `table-in-doc-not-code` (fail — claimed table doesn't exist)
- `column-mismatch` (info — column types or names differ)

**Effort:** ~600 lines
**Risk:** medium-high — ORM patterns vary; migrations can be intricate
**Acceptance:** Aigent backend's 8 documented tables match models;
any new tables since the doc was edited get flagged

---

### PR #7 — Bug-ref crosscheck

**Goal:** ensures bug IDs cited in code (e.g. `# BUG-014: workaround`
or `# fixes BE-0413`) have entries in `docs/bug-registry.md`, and
vice-versa.

**Files**

| Path | Purpose |
|---|---|
| `src/dotagent/code/crosschecks/bug_refs.py` | Compare logic |
| `src/dotagent/code/extractors/code_bug_refs.py` | Grep for bug-ID patterns in comments |
| `tests/code/test_bug_refs_crosscheck.py` | 10 tests |

**Detection**

Code-side: regex grep for bug-prefix patterns from `.agent/config.yaml::bugs.id_prefix`:
- `# BUG-XXX`, `# BE-NNNN`, `# fixes DA-BUG-0123`
- Also `// BUG-XXX` for JS/TS

Doc-side: parsed bug-registry entries (already exists via `sources.py`).

**Drift categories**

- `bug-in-code-not-registry` (warn — undocumented active bug)
- `bug-in-registry-status-fixed-but-code-still-references-it`
  (info — code may be stale; cleanup candidate)
- `cross-repo-bug-not-in-this-registry` (info — pointer up to project root)

**Effort:** ~350 lines
**Risk:** low — regex grep + lookup
**Acceptance:** Aigent's 380+ DA-BUG refs in backend code reconcile against the bug-registry

---

### PR #8 — Doctor integration + `--write` auto-fix + TypeScript

**Goal:** polish phase. Three concerns:

1. `dotagent doctor` surfaces drift count
2. `--write` on `code audit` applies safe count corrections
3. TypeScript crawler (Next.js routes, exports)

**Files to modify / create**

| Path | Purpose |
|---|---|
| `src/dotagent/doctor.py` | New `_check_code_drift()` |
| `src/dotagent/code/audit.py` | `--write` execution path |
| `src/dotagent/code/typescript_walker.py` | TS AST walker (next.js routes + exports) |
| `tests/code/test_doctor_integration.py` | 5 tests |
| `tests/code/test_auto_fix.py` | 8 tests |
| `tests/code/test_typescript_walker.py` | 10 tests |

**`--write` rules**

ONLY safe corrections are auto-applied:

- Count corrections in plain text (`22 agents` → `23 agents`)
- Count corrections in markdown tables (`| Count | 22 |` → `| Count | 23 |`)

NEVER auto-applied:

- Adding or removing route entries
- Adding or removing redis namespaces
- Adding or removing table entries
- Anything that changes lists, not just numbers

Each `--write` change is logged to `.agent/.code-audit-log.md` with
the doc path, line number, before/after, and timestamp. Reversible
via manual edit.

**TypeScript scope**

Phase 1 minimum:
- Detect `app/*/route.ts` and `pages/api/*.ts` (Next.js)
- Detect exports + their types
- Output schema matches the Python walker's

Defer: full TypeScript AST walk, decorator extraction, JSX scanning.

**Effort:** ~700 lines
**Risk:** medium — `--write` touches user files; needs heavy testing
**Acceptance:** running `dotagent code audit --write` on Aigent fixes
the agent-count drift in all three docs and logs each change

---

## Total effort

| Phase | PRs | Estimated lines |
|---|---|---|
| 1 — Foundation | #1, #2 | ~1,600 |
| 2 — Crosschecks | #3, #4, #5, #6, #7 | ~2,300 |
| 3 — Polish | #8 | ~700 |
| **Total** | **8** | **~4,600** |

At a sustainable pace: **4–6 weeks** including review and the
end-to-end testing the user audit demands.

---

## Release plan

Single minor release: **v0.5.0**. Reasoning:

- All 8 PRs deliver complementary value; releasing them piecemeal
  fragments the audit chain.
- v0.5.0 unlocks a real "is your project healthy?" answer that today's
  v0.4.x can't give.
- Schema version stays at `0.4.0` (no migration needed; only additive
  config + new commands).

Per-PR patch releases (v0.4.6 / v0.4.7) could ship if any one PR has
urgent demand, but the default is batch-ship as v0.5.0.

---

## Backward compatibility commitments

1. Existing dotagent users keep working. The `code:` config block is
   opt-in; `code.enabled: false` (default if absent) means no scanning.
2. The 480 existing tests must remain green.
3. `dotagent doctor` continues to exit 0/1 the same way; the new
   code-drift check is non-fatal (info / warn only).
4. No file is moved or renamed. The new `.agent/.cache/code_index.json`
   is the only new on-disk artifact (and it's gitignored).
5. `CLAUDE.md` rendering adds a new "Code reality" section but only
   when there are findings — clean projects render unchanged.

---

## Risks + mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Python AST parsing fails on unusual code (decorators-on-decorators, dynamic routes) | medium | medium | Catch exceptions; log; skip the file; per-file failure isolation |
| `--write` corrupts a doc | low | high | Auto-fixes restricted to single-number replacements; full diff logged; refuses if multiple count claims on the same line |
| Crosscheck false positives create alert fatigue | high | medium | Each crosscheck supports `code.crosschecks.<name>.ignore_patterns`; defaults are conservative |
| Index gets stale + audit reports phantom drift | medium | medium | Cache mtime checked against scanned-file mtimes; staleness flagged in `doctor` |
| TypeScript walker is more complex than scoped | high | medium | TypeScript walker is intentionally minimum-viable in #8; full coverage deferred to a later PR |
| Monorepo with 50k+ files slow to scan | medium | low | Scan walks honors excludes; tests include a 5k-file fixture to catch perf regressions; documented as "v1 targets <10k files" |
| Doc-claim extraction misses valid claims | high | low | Conservative defaults; user can add custom patterns in config; LLM extraction stays Coda's job |
| Conflicting crosscheck configurations across services in layered project | low | medium | Each service repo gets its own scan; project-root rollup aggregates |

---

## Configuration reference

Full `.agent/config.yaml` additions:

```yaml
code:
  enabled: true                        # default false until 0.5.0 ships in user repo

  scan_roots: ["src/", "app/"]         # dirs to walk
  excludes:
    - "**/__pycache__"
    - "**/.venv"
    - "**/node_modules"
    - "**/test_*.py"
    - "**/*.test.ts"
  languages: ["python", "typescript"]  # crawler dispatch

  cache_max_age_days: 7                # doctor warns if older

  crosschecks:
    counts:
      enabled: true
    routes:
      enabled: true
      frameworks: ["fastapi", "flask"]
    redis:
      enabled: true
    database:
      enabled: true
      orm: "sqlalchemy"
      migrations_dir: "alembic/versions"
    bugs:
      enabled: true

  count_mappings:                      # for PR #3
    agents:
      glob: "src/backend/dotagent_agents/*.py"
      exclude: ["**/__init__.py", "**/base.py"]
    services:
      glob: "services/*/"
      kind: "dir"
```

---

## Sign-off

Approve this plan by replying with:

1. **"approved"** — I start PR #1 immediately
2. **"approved, but defer X"** — name any PRs to push past 0.5.0
3. **"revise"** — what to change (scope, ordering, locked decisions)

Open questions before I start, if any:

1. **Should #3 (counts) ship as a 0.4.6 patch to unblock Aigent immediately?** It's
   the single highest-leverage crosscheck and standalone. Trade-off:
   ships less-tested without the umbrella audit framework.
2. **TypeScript scope in #8** — minimum-viable (Next.js routes only) or
   full TS AST walker? Default: minimum-viable; expand in a follow-up.
3. **Auto-fix rules** — should `--write` also fix list-of-routes drift
   (adding a missing route to a markdown table), or strictly counts
   only? Default: counts only for v1. Lists deferred.
4. **`.agent/.cache/code_index.json` size** — for Aigent's ~1,200
   files, expect ~500KB. For monorepos >10k files, may need chunking.
   Default: single file v1; chunking deferred.
