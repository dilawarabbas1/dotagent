# `dotagent doc-coverage` — required-doc checklist CLI

_Status: shipped in v0.4.12 · last updated 2026-05-20_

A read-only CLI that returns the hand-maintained docs an agent should
consider updating for a given changed-file set. Designed to be called
by the Coda orchestrator's doc-maintenance gate (Prompt 2 field #4),
or used standalone for git-hook / PR-review workflows.

The command NEVER writes to any file. It reads:
- `docs/feature_master.md` + `docs/feature_master/FM-###-<slug>.md` (the
  hand-maintained feature index — see `HAND_MAINTAINED_DOCS_CONVENTION.md`)
- The changed-file paths you pass via `--files`
- Optionally the commit message via `--commit-msg`

…and returns a structured checklist with severity-tagged guidance.

---

## Usage

```bash
dotagent doc-coverage \
    --files "$(git diff --cached --name-only | tr '\n' ',')" \
    --commit-msg "$(git log -1 --pretty=%s)" \
    --format json
```

CLI flags:

| Flag | Description |
|---|---|
| `--files` (required) | Repo-relative paths, comma- or newline-separated. |
| `--format` | `json` (default, for orchestrator) · `markdown` (pasteable into Prompt 2 / PR) · `text` (terminal-friendly). |
| `--commit-msg` | Optional commit message. Detects `DA-BUG-LAYER-NNN` tokens and adds the matching bug-registry shard. |
| `--repo` | Repo root override. Default: auto-discover via `.agent/`. |
| `--severity` | Filter: `all` (default) · `hard` · `suggested+` (HARD+SUGGESTED, no CHECK noise). |

---

## Severity model

Every required-doc entry carries one of three severities:

| Severity | Glyph | Meaning |
|---|---|---|
| `hard` | 🔴 | The file is explicitly declared in an FM-###'s `files:` section. The agent MUST update that feature's record if behaviour, route, deps, or invariants changed. |
| `suggested` | 🟡 | Heuristic match (DB-ish path, Redis-ish, host/route, etc.). Agent should review and update if applicable. |
| `check` | 🟢 | Always-applicable check (anti-patterns invariant scan, bug-registry on bug-fix commits). Cheap to skim, rarely produces an actual edit. |

Use `--severity hard` when you want the strict gate (FM-### coverage
only). Use `--severity suggested+` to skip CHECK noise but keep the
deep registry suggestions. Use `--severity all` (default) when running
inside the orchestrator's doc-maintenance prompt — Claude needs every
prompt to acknowledge.

---

## How the mapping works

### HARD severity — FM-### `files:` parsing

For every `docs/feature_master/FM-*.md`:
1. Extract the FM-### id from the filename.
2. Walk the file looking for a `## files` (or `## Files:`, `### files`, etc.) heading.
3. Until the next heading, collect every backtick-quoted token that looks like a path (contains `/`, `.`, or `*`). Skip tokens like `users` (table names) or `DB_URL` (env vars).
4. Build a map: declared-path → [FM-###]. Glob support: `*` matches anything but `/`; `**` matches anything including `/`.

For each input file, find every FM-### whose `files:` section claims
it (directly or via glob). Emit one HARD entry per match pointing at
the actual `FM-NNN-<slug>.md` filename.

### SUGGESTED severity — join-key heuristics

Pure regex rules over the input file path:

| Pattern (case-insensitive) | Suggested docs |
|---|---|
| `(?:^\|/)(?:db\|database\|models\|migration\|repos\|schema\|sql\|orm)(?:/\|$\|\.)` | `db-impact-map-{master,tenant,vector}.md` |
| `(?:^\|/)(?:redis\|cache)(?:/\|$\|\.)` or `redis_client` / `redis.` | `redis-key-registry-{tenant,global,events}.md` |
| `(?:^\|/)(?:routes\|controllers\|api\|handlers\|endpoints)(?:/\|$\|\.)` | `feature_master/FM-###-<slug>.md` (files: section confirmation) |
| `(?:^\|/)(?:pm2\|ecosystem\|docker\|deploy\|nginx)` or `(?:server\|worker\|daemon\|consumer\|producer)\.(py\|ts\|js\|mjs)` | `ops/service-registry.md` |

If multiple rules match the same file, all corresponding docs are
suggested (deduplicated).

### CHECK severity — always-applicable

- `docs/anti-patterns.md` — always present. Cheap reminder to check
  whether the change introduces or fixes an anti-pattern.
- `docs/bug-registry-{infrastructure,agents,orchestrator}.md` — added
  when the `--commit-msg` value contains a `DA-BUG-LAYER-NNN` (or
  `BUG-LAYER-NNN`) token. Layer maps:
  - `INFRA` / `INFRASTRUCTURE` → `bug-registry-infrastructure.md`
  - `AGT` / `AGENTS` → `bug-registry-agents.md`
  - `ORCH` / `ORCHESTRATOR` → `bug-registry-orchestrator.md`

---

## Unmapped files

Files that match no FM-### appear in `unmapped_files` (alongside the
per-file `FileCoverage` with `fm_ids: []`). The Markdown output ends
with an explicit "Unmapped files" section directing the agent to
either:
1. Add the file to an existing `FM-###-<slug>.md` `files:` section, or
2. Declare a new FM-### for the feature it belongs to.

The orchestrator's doc-maintenance gate (Coda side) should treat
non-empty `unmapped_files` as a coverage gap.

---

## Output shapes

### JSON (default — for orchestrator consumption)

```json
{
  "files": [
    {
      "path": "src/auth.py",
      "fm_ids": ["FM-014"],
      "required_docs": [
        {
          "path": "docs/feature_master/FM-014-auth.md",
          "severity": "hard",
          "reason": "`src/auth.py` is declared in FM-014's `files:` section — update that feature's record if behaviour, route, deps, or invariants changed."
        },
        {
          "path": "docs/anti-patterns.md",
          "severity": "check",
          "reason": "Always: review whether this change introduces or fixes an anti-pattern."
        }
      ]
    }
  ],
  "unmapped_files": [],
  "warnings": []
}
```

### Markdown (pasteable)

```markdown
# Doc-coverage checklist

## `src/auth.py`
**FM-###:** `FM-014`

- 🔴 HARD — `docs/feature_master/FM-014-auth.md`
  - `src/auth.py` is declared in FM-014's `files:` section — update that feature's record …
- 🟢 CHECK — `docs/anti-patterns.md`
  - Always: review whether this change introduces or fixes an anti-pattern.
```

### Text (terminal-friendly)

```
=== src/auth.py
    FM-### : FM-014
    🔴 HARD  docs/feature_master/FM-014-auth.md
        → `src/auth.py` is declared in FM-014's `files:` section …
```

---

## Hard boundary — never writes

The command is read-only by design. Test
`test_doc_coverage_never_writes_anything` snapshots the entire repo's
file mtimes + contents before invoking `doc-coverage`, then asserts
nothing changed: no mtime touch, no content edit, no new files.

If you find a write path, **that's a bug** — file an issue.

---

## How Coda uses this

Inside the orchestrator's `doc_maintenance_running` stage:

```python
# Pseudocode for Coda's doc-maintenance prompt builder
files = git_diff_files(cycle.start_sha, cycle.handoff_sha)
checklist_json = run_cli([
    "dotagent", "doc-coverage",
    "--files", ",".join(files),
    "--commit-msg", cycle.commit_msg,
    "--format", "json",
])
prompt2_field4 = render_checklist_for_claude(checklist_json)
```

The orchestrator then sends Prompt 2 (with `prompt2_field4` populated)
to Claude. Claude either:
- Updates each HARD doc + reviews SUGGESTED + skims CHECK, then posts
  `coverage_complete: true` with rationale, OR
- Posts `coverage_complete: false` with `skipped_files[]` + per-file
  rationale.

See the Coda side for the FSM stage / hook handler / failure semantics.

---

## Limitations

1. **Parser is tolerant, not strict.** If your FM-###-<slug>.md doesn't
   use a `## files` heading, files aren't extracted. Add the heading or
   the file shows up as `unmapped_files`.
2. **No content-aware analysis.** The mapper sees file paths, not file
   contents. A file named `src/foo.py` that imports redis won't match
   the Redis heuristic. (Content-aware would be a v0.5+ enhancement
   if the tradeoff is worth it.)
3. **No diff-aware suggestions.** The mapper sees the full file path
   list, not what changed inside each file. A 1-line typo fix and a
   500-line rewrite get the same checklist. The agent applies judgement.
4. **Bug-registry routing relies on commit-msg conventions.** If your
   project doesn't use `DA-BUG-LAYER-NNN` tokens, pass `--commit-msg ""`
   to suppress bug-registry suggestions.

---

## Related docs

- `HAND_MAINTAINED_DOCS_CONVENTION.md` — the convention `doc-coverage` reads.
- `CLAUDE_MD_DESIGN.md` — overall ownership model.
- `src/dotagent/coverage.py` — parser + heuristic mapper (pure functions).
- `src/dotagent/commands/doc_coverage_cmd.py` — CLI surface.
- `tests/test_doc_coverage.py` — 29 tests covering parser, heuristics,
  CLI formats, severity filter, no-write boundary.
