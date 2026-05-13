# Auto-Dream

The agent-learning loop. Episodic experience → candidate patterns → human
review with **mandatory written rationale** → graduated semantic rules
that flow into every future CLAUDE.md.

## The loop in one paragraph

`dotagent dream run` looks at the last 30 days of episodic memory, finds
clusters (reverts grouped together, files that keep getting fix-touched,
recurring error types, bug-registry entries hit by multiple actors), and
writes one candidate file per cluster into `.agent/dream/candidates/`.
You review each candidate and either `graduate` it (becomes a rule the AI
follows forever) or `reject` it (kept as an audit record of what wasn't
worth a rule). Every decision requires a written rationale — that rationale
file is the audit trail of what your agent has learned.

## What signals get extracted

### Heuristic (always on)

| Signal | Triggers when |
|--------|--------------|
| `revert_cluster` | ≥ 2 revert events in window |
| `repeat_fix` | Same file fix-touched ≥ 3 times |
| `frequent_failure` | Same error name appears in ≥ 3 events |
| `cross_actor_anti` | Bug-registry entry hit by ≥ 2 different actors |

### Semantic (opt-in via `pip install 'dotagent[ml]'`)

| Signal | What it does |
|--------|--------------|
| `semantic_cluster` | sentence-transformers embeddings (`all-MiniLM-L6-v2`) + sklearn DBSCAN on cosine distance, clusters events with related summaries even when files / errors don't match. |

The heuristic version catches the obvious; semantic catches the subtle
("fix auth bug" and "JWT validation broken" cluster together).

## Daily workflow

```bash
# extract signals (no API key needed)
dotagent dream run --since 30d

# see what landed
dotagent dream list

# review each one (open the .agent/dream/candidates/<id>.md in your editor)
# then decide:
dotagent dream graduate <id> --rationale "Recurring fix indicates a missing test gate; add coverage requirement for services/auth/*"
dotagent dream reject   <id> --rationale "Three independent bugs, not a pattern — coincidence"

# graduations flow into the next sync
dotagent sync
```

## The rationale is not optional

`graduate` and `reject` both raise an error if `--rationale` is empty or
missing:

```bash
$ dotagent dream graduate abc123 --rationale ""
Error: rationale is required for graduation — non-negotiable
```

Why: a graduated rule will influence every future AI session on every
teammate's machine. Without a written rationale you'd never know why a
specific behavior was prescribed six months from now. The rationale file
*is* the audit of what your team has learned.

## What graduation produces

When you graduate candidate `abc123`:

1. The candidate file is moved from `.agent/dream/candidates/abc123.md`
   to `.agent/dream/graduated/abc123.md`, with `## Rationale` and
   `## Graduated by` sections appended.
2. A new entry is written under `.agent/memory/semantic/rules/auto-dream/`
   with content-hashed slug. This is what the renderer pulls into the
   "Patterns (graduated knowledge)" section of CLAUDE.md.

Both files are committed to git. Every teammate gets the new rule on
their next `git pull && dotagent sync`.

## What rejection produces

`.agent/dream/rejected/<id>.md` with `## Rejection rationale` appended.
Stays as an audit record so you don't re-propose the same pattern next
month.

## Running on a schedule

### Local cron

```bash
dotagent dream cron-install                # daily at 02:00 UTC
dotagent dream cron-install --schedule "0 9 * * 1"   # Mondays at 09:00
dotagent dream cron-uninstall              # remove this repo's entry
```

The cron line is per-repo. Multiple projects → multiple cron lines.

### GitHub Actions (recommended for teams)

```bash
dotagent dream github-action               # writes .github/workflows/dotagent-dream.yml
git add .github/workflows/dotagent-dream.yml
git commit -m "ci: dotagent dream nightly"
```

The workflow runs nightly, opens a PR with new candidates, and you review
+ graduate them in the PR (which has the candidate markdown files as the
diff). When merged, the new rules flow into CLAUDE.md on the next sync.

## What good rationale looks like

**Good:**

> Across three reverts in the last 14 days, the breaking change was a
> column rename without a backfill migration. Graduate: "schema changes to
> shared columns require a backfill migration in the same PR". Evidence:
> commits abc123, def456, 789xyz.

**Bad:**

> seems important
> agree, ship it

A rule with no rationale is worse than no rule — six months from now no
one will know whether to keep, modify, or remove it. dotagent enforces
this on purpose.

## Tuning

`.agent/config.yaml`:

```yaml
dream:
  min_cluster_size: 3        # heuristic threshold
  window_days: 14            # default window for `dream run`
```

Or pass `--min-cluster-size N --since 60d` to `dream run` directly.

## Next

- **[[Memory Model]]** — where graduated rules live, how they flow into adapters
- **[[Commands Reference]]** — every `dream` subcommand
- **[[Server and RBAC]]** — surfacing dream candidates across multiple repos
