"""Invariant text blocks for the CLAUDE.md navigation manifest.

These are the same across every project — only template placeholders
({meta_branch}, {bug_prefix}, etc.) differ. The renderer fills them in.

Three blocks:

- HOW_TO_READ_PROTOCOL: numbered sequential reading instructions
- WORKFLOW_CONTRACT:    before/during/after lifecycle with mandatory
                        post-task doc updates (Claude's responsibility)
- HARD_POLICY:          the never-violate list with rationale

The key framing throughout: dotagent provides the framework and the
checklist; CLAUDE (you, the AI) writes the actual doc content. Generated
files (CLAUDE.md, SCOPE.md, etc.) are dotagent's; source docs
(`docs/*.md`, `.agent/*.md`, contracts, handoffs) are Claude's.
"""

from __future__ import annotations


HOW_TO_READ_PROTOCOL = """\
═══════════════════════════════════════════════════════════════════════════
  📖  HOW TO READ THIS FILE  (do this first, every session)
═══════════════════════════════════════════════════════════════════════════

This file is a NAVIGATION MANIFEST. It does NOT contain project content
inline. It tells you WHICH files to read for which task. Read pointers,
not content.

Your reading protocol — follow IN ORDER at the start of every session:

  1. Read this entire CLAUDE.md (you are here)
  2. Read EVERY file listed under "🔴 MUST READ" below
  3. Read `CLAUDE.local.md` if it exists (your per-session sidecar; gitignored)
  4. Read `.agent/git.md` to understand branch rules + push policy
  5. Identify what you've been asked to do, then jump to the matching
     "Where to find what" section — follow pointers as needed.

If a pointer leads to a file > 500 lines, read it in chunks; don't try
to hold all of it in working memory at once.
"""


# `{meta_branch}` and `{bug_prefix}` filled per-project at render time.
WORKFLOW_CONTRACT_TEMPLATE = """\
═══════════════════════════════════════════════════════════════════════════
  🔁  WORKFLOW CONTRACT  (read once, follow every task)
═══════════════════════════════════════════════════════════════════════════

You are operating inside a dotagent-managed project with a strict dev↔QA
cycle. Every task — feature work, bug fix, refactor — follows this loop.

OWNERSHIP RULE (read carefully):

  • dotagent writes GENERATED files (CLAUDE.md, SCOPE.md, CONTRACTS.md,
    git.md, the brief's Modules table). You never edit these.

  • YOU (Claude) write CONTENT files:
      - `docs/*.md` (bug-registry, anti-patterns, redis-keys, db-impact-map,
        dependency-map, architecture) — these are the project's truth;
        dotagent never writes here. Keeping them current is YOUR job.
      - Cycle artifacts (contract.md, dev-handoff.md, qa-findings.md) —
        you write through dotagent CLI commands.

──────────────────────────────────────────────────────────────────────
BEFORE coding
──────────────────────────────────────────────────────────────────────

  • Confirm the contract exists and is frozen:
      `.agent/project/modules/<id>/cycles/<NN>/contract.frozen.md`
  • If absent, the cycle hasn't been agreed — STOP and report.
  • Re-read the contract's Scope, Acceptance criteria, Must-not-regress,
    and Business-traceability sections. Cite FEAT-NN + OBJ-NN in your work.

──────────────────────────────────────────────────────────────────────
DURING coding
──────────────────────────────────────────────────────────────────────

  • Stay within the contract's Scope and Acceptance criteria.
  • Respect every RULE-NN cited in the brief.
  • If you discover a scope conflict, ADD a note in the cycle's
    `dev-handoff.md` later — do not silently expand scope.
  • If you must violate a rule, STOP and ask. Never silently bypass.

──────────────────────────────────────────────────────────────────────
AFTER coding — MANDATORY documentation updates  ✱✱✱
──────────────────────────────────────────────────────────────────────

✱ YOU write these updates. dotagent does NOT do this for you. ✱

Before you handoff to QA, run through this checklist. None are optional —
they are part of "done" for any task:

  ☐ Did you fix a bug?
    → YOU edit `docs/bug-registry.md` (or the relevant service's):
        - mark `status: fixed`
        - add `fix-frozen: <today's date>` and `fix-sha: <commit-sha>`
        - if you added a guard test, list its filename

  ☐ Did you add or change a Redis namespace?
    → YOU edit `docs/redis-keys.md`:
        - add an H2 entry with TTL + owner + tenant-scoping note
        - cite the RULE-NN it respects (typically RULE-01 tenant isolation)

  ☐ Did you touch a DB table or add a migration?
    → YOU edit `docs/db-impact-map.md`:
        - add the table to the relevant shard map
        - update blast-radius rating if appropriate
        - confirm migration number + rollback line are in the contract

  ☐ Did you add or change a service-to-service call?
    → YOU edit `docs/dependency-map.md`.

  ☐ Did you identify an anti-pattern (yours or pre-existing)?
    → YOU edit `docs/anti-patterns.md` with rationale.

  ☐ Did you change a route / API contract?
    → YOU edit `docs/architecture.md` §API.
    → YOU edit `docs/shared-contracts.md` if cross-service.

  ☐ Did you discover a new project-wide rule?
    → file it as a candidate: `dotagent dream graduate <id> --rationale "..."`
    → do NOT edit `.agent/rules.md` directly — the graduation gate
      enforces a written rationale.

  ☐ Did module state change?
    → do NOT hand-edit `module.yaml` — use the dotagent CLI:
      `dotagent project handoff <id>` · `dotagent project resolve <id>`

  ☐ Finally: run `dotagent sync` so generated adapter files
    (CLAUDE.md, .cursorrules, etc.) pick up your `docs/` and `.agent/`
    edits. If you skip this, the next session reads a stale CLAUDE.md.

──────────────────────────────────────────────────────────────────────
HANDOFF to QA
──────────────────────────────────────────────────────────────────────

Run: `dotagent project handoff <module-id>`

This writes `cycles/<NN>/dev-handoff.md` for QA to read. YOU then EDIT
that file to include:

  - What you changed (one bullet per acceptance criterion)
  - How to test it (exact commands: `pytest path/to/test.py`, `curl -i ...`)
  - Any deviations from the contract + rationale
  - Updated doc paths (so QA knows what to re-read)

──────────────────────────────────────────────────────────────────────
WAIT for QA approval
──────────────────────────────────────────────────────────────────────

QA writes `cycles/<NN>/qa-findings.md` via:
  `dotagent project qa-record --result pass|fail --rationale "..."`

QA's rationale is MANDATORY — dotagent refuses to record without it.
Wait for QA before pushing.

──────────────────────────────────────────────────────────────────────
ONLY ON `qa-record --result pass`
──────────────────────────────────────────────────────────────────────

  1. Read `.agent/git.md` to confirm:
     - which branch you may push to
     - which paths are forbidden on this branch
  2. Push: `git push origin <branch>`
     - The pre-push hook (if installed) runs `dotagent git verify`.
     - If it rejects you, you violated branch rules — DO NOT use
       `--no-verify`. Fix the violation instead.

──────────────────────────────────────────────────────────────────────
IF `qa-record --result fail`
──────────────────────────────────────────────────────────────────────

  1. Read `cycles/<NN>/qa-findings.md` carefully.
  2. Open the next cycle: `dotagent project start <module-id>`
     (auto-bumps to cycle <NN+1>)
  3. Fix every finding · return to "BEFORE coding" for the new cycle.
"""


HARD_POLICY = """\
═══════════════════════════════════════════════════════════════════════════
  🚫  HARD POLICY  (never violate · enforced where dotagent can)
═══════════════════════════════════════════════════════════════════════════

  ✗  NEVER push code to a meta branch (see `.agent/git.md`).
  ✗  NEVER push without QA-pass recorded via `dotagent project qa-record`.
  ✗  NEVER use `git push --no-verify` to bypass the dotagent pre-push hook.
  ✗  NEVER hand-edit a file with a `<!-- generated by dotagent -->` banner.
     Edit the source-of-truth file it derives from, then run `dotagent sync`.
  ✗  NEVER graduate a semantic rule without `--rationale "..."` —
     dotagent refuses.
  ✗  NEVER record `qa-record --result pass` without `--rationale "..."` —
     dotagent refuses.
  ✗  NEVER freeze a contract without convergence — use `--force` only with
     a written rationale (`--rationale "executive override because..."`).
  ✗  NEVER edit `contract.frozen.md` — it's immutable by design.
  ✗  NEVER skip the post-task doc-update checklist. Stale docs lie to
     the next AI agent and to your teammates.
"""


# ---------------------------------------------------------------------------
# Code-graph awareness (dotgraph integration, v0.5.3+)
# ---------------------------------------------------------------------------
#
# Injected into rendered adapters when `.dotgraph/graph.db` is detected at the
# project root. Tells the agent which MCP tools are available + which static
# docs dotgraph maintains. The MCP server config snippet itself is NOT
# included here — that's the consumer's job (Coda generates per-spawn, Cursor
# users use `dotgraph mcp-config --tool cursor`, etc.).
#
# Tool names are unprefixed; the runtime adds its own namespace prefix (e.g.
# `mcp__dotgraph__context_pack`).

CODE_GRAPH_AWARENESS_BLOCK = """\
═══════════════════════════════════════════════════════════════════════════
  🕸  CODE-GRAPH AWARENESS  (dotgraph)
═══════════════════════════════════════════════════════════════════════════

This project is indexed by **dotgraph** (`.dotgraph/graph.db` present at the
repo root). When a runtime exposes dotgraph's MCP server, these tools are
available:

  · `context_pack(task_description)` — call FIRST before reading or
    grepping files. Returns ranked candidate symbols and file hints for
    the task. Don't blind-grep.
  · `impact(symbol, depth=2)` — blast radius for a symbol: callers,
    callees, tests, data touchpoints. Use the result to populate the
    contract's `callers_to_update` and `tests_to_update` sections.
  · `reconcile(changed_paths, claimed)` — diff your stated impact against
    the structural impact. Downstream gates may run this after your cycle.
    Enumerate Surfaces honestly upfront — see `## Surfaces` in your
    contract.md.
  · `find_refs(needle)` — content-FTS safety net for dynamic dispatch,
    reflection, and computed names the static extractor cannot resolve.
  · `search(query, kind)` — name / signature / summary lookup.

Static graph snapshots refreshed on `dotagent sync`:
  · `docs/dependency-map.md`     — module + service dependency edges
  · `docs/db-impact-map.md`      — file → table · column · R/W matrix
  · `docs/redis-key-registry.md` — key patterns + owners + TTLs
  · `docs/kafka-topics.md`       — topic publishers / consumers
  · `docs/endpoints.md`          — HTTP routes + handler nodes

These are generated by `dotgraph emit-docs`; do NOT hand-edit them.
"""


def code_graph_awareness_block(repo_root) -> str:
    """Return the awareness block if `.dotgraph/graph.db` exists, else "".

    Filesystem check only — does NOT shell out to dotgraph. Renders are
    expected to be deterministic and side-effect-free.
    """
    from pathlib import Path
    db = Path(repo_root) / ".dotgraph" / "graph.db"
    return CODE_GRAPH_AWARENESS_BLOCK if db.exists() else ""


__all__ = (
    "HOW_TO_READ_PROTOCOL",
    "WORKFLOW_CONTRACT_TEMPLATE",
    "HARD_POLICY",
    "CODE_GRAPH_AWARENESS_BLOCK",
    "code_graph_awareness_block",
)
