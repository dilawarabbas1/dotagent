# `dotagent doc-coverage`

Read-only CLI that returns the hand-maintained docs an agent should update for a given changed-file set. Reads the `feature_master` structure (see `HAND_MAINTAINED_DOCS_CONVENTION.md`); writes nothing.

Designed as the dotagent-side piece of Coda's doc-maintenance orchestration gate; useful standalone for git hooks / PR-review.

---

## Usage

```bash
dotagent doc-coverage \
    --files "$(git diff --cached --name-only | tr '\n' ',')" \
    --commit-msg "$(git log -1 --pretty=%s)" \
    --format json
```

| Flag | Description |
|---|---|
| `--files` (required) | Repo-relative paths, comma- or newline-separated |
| `--format` | `json` (default) · `markdown` (pasteable) · `text` (terminal) |
| `--commit-msg` | Optional. Detects `DA-BUG-LAYER-NNN` tokens → adds matching bug-registry shard |
| `--severity` | `all` (default) · `hard` · `suggested+` (HARD+SUGGESTED, no CHECK) |
| `--repo` | Override auto-discover via `.agent/` |

---

## Severity model

| Severity | Glyph | When |
|---|---|---|
| `hard` | 🔴 | File is in an FM-###'s `## files` section. **Must** update that feature's record. |
| `suggested` | 🟡 | Heuristic match (DB/Redis/host/route path patterns). Review and update if applicable. |
| `check` | 🟢 | Always-applicable (`anti-patterns.md` invariant scan + `bug-registry-*` on bug-fix commits). |

---

## Mapping rules

**HARD** — walks `docs/feature_master/FM-*.md`, finds each file's `## files` heading (case-insensitive; tolerates `## Files:`, `### files`, etc.), extracts backtick-quoted path tokens (must contain `/`, `.`, or `*`). Builds path→[FM-###] map with glob support (`*` matches non-`/`; `**` matches everything).

**SUGGESTED** — regex heuristics over file path:

| Pattern | Suggested docs |
|---|---|
| `db / database / models / migration / repos / schema / sql / orm` | `db-impact-map-{master,tenant,vector}.md` |
| `redis / cache / redis_client / redis.` | `redis-key-registry-{tenant,global,events}.md` |
| `routes / controllers / api / handlers / endpoints` | `feature_master/FM-###-<slug>.md` (files: confirmation) |
| `pm2 / ecosystem / docker / deploy / nginx` or `server/worker/daemon/consumer/producer.{py,ts,js,mjs}` | `ops/service-registry.md` |

**CHECK** — always emits `docs/anti-patterns.md`. Adds `docs/bug-registry-{infra,agents,orch}.md` when `--commit-msg` contains `DA-BUG-LAYER-NNN`. Layer maps: `INFRA/INFRASTRUCTURE` · `AGT/AGENTS` · `ORCH/ORCHESTRATOR`.

---

## Output (JSON — default)

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

`unmapped_files` lists changed files no FM-### claims. The orchestrator's gate should treat non-empty `unmapped_files` as a coverage gap — the agent either adds the file to an existing `FM-###-<slug>.md` `files:` section or declares a new FM-###.

Markdown and text formats render the same data; markdown is pasteable into a PR comment or orchestrator prompt.

---

## Hard boundary — never writes

Test `test_doc_coverage_never_writes_anything` snapshots every file's mtime + content before invoking, asserts byte-for-byte unchanged after. If you find a write path, **that's a bug**.

---

## Limitations

1. **Parser is tolerant, not strict.** If your `FM-###-<slug>.md` lacks a `## files` heading, files aren't extracted → they show up as `unmapped_files`.
2. **Path-based only, not content-aware.** A file named `src/foo.py` that imports redis won't match the Redis heuristic.
3. **No diff-aware suggestions.** A 1-line typo fix and a 500-line rewrite get the same checklist. Agent applies judgement.
4. **Bug-registry routing needs commit-msg conventions.** No `DA-BUG-LAYER-NNN` token → no bug-registry suggestion.

---

## Related

- `HAND_MAINTAINED_DOCS_CONVENTION.md` — the convention `doc-coverage` reads
- `src/dotagent/coverage.py` — parser + heuristic mapper (pure)
- `src/dotagent/commands/doc_coverage_cmd.py` — CLI surface
- `tests/test_doc_coverage.py` — 29 tests (parser · heuristics · CLI · no-write boundary)
