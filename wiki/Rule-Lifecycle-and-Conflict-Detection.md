# Rule Lifecycle and Conflict Detection

> Built in response to [Faisal Feroz's feedback](https://www.linkedin.com/pulse/four-memory-model-makes-ai-coding-agents-finally-remember-abbas-fby2c/)
> on the LinkedIn article: the semantic layer with mandatory rationale is a
> graveyard of stale conventions unless paired with (a) expiration and review
> cycles, and (b) conflict detection between working memory and what semantic
> memory says is the team standard.
>
> Both are now shipped. This page explains how they work and how to use them.

---

## Why this matters

Every team that adopts AI coding context hits two failure modes within the
first six months:

1. **Stale rules.** A rule graduated when the codebase looked one way; the
   code has since moved; nobody remembered to retire or update the rule;
   agents keep enforcing it; devs lose trust in the system.

2. **Silent contradiction.** Working memory says "developer is editing
   `services/api/controllers.py` right now." Semantic memory says "ANTI-001
   forbids direct DB writes from controllers." The AI agent's reasoning
   *might* notice — but humans reviewing the diff have no signal that the
   compliance check was made.

dotagent now addresses both directly.

---

## Conflict Detection (Module 1)

**What it is.** Before any change lands, the rendered `CLAUDE.md` (and every
other adapter output) surfaces a `⚠ Rule conflicts in active edits` section
when the active developer's `current.recent_files` overlap with files cited
by semantic rules / bug-registry entries / anti-patterns.

**What it looks like in CLAUDE.md:**

```markdown
## ⚠ Rule conflicts in active edits

_The files you're currently editing are cited by these rules. Review each
before the next handoff — these are not informational; they are constraints
on the change you're making._

- **BUG-007** — 🔴 CRITICAL — _bug-registry_ — Stale JWT cache
  - Touched in this session: `services/auth/jwt.py`, `services/cache/redis.js`
  - Source: `docs/bug-registry.md`
  - Action: Verify the change does not regress BUG-007 (see body of the entry).

- **ANTI-001** — 🟠 HIGH — _anti-pattern_ — Direct DB writes from controllers
  - Touched in this session: `services/api/controllers.py`
  - Source: `docs/anti-patterns.md`
  - Action: Review ANTI-001 before merging — your change touches files this pattern forbids.
```

**When it fires.**

- `current.recent_files` is non-empty AND
- One or more files in that list appears in the `files:` metadata of a
  bug-registry entry or anti-pattern.

**When it does not fire.**

- Working memory is empty (fresh session, no edits yet) → section suppressed.
- Edited files have no rule citations → section suppressed.
- (Suppression is by design — a noisy section trains agents and humans to skip it.)

**Configuration.**

```yaml
# .agent/config.yaml
context:
  conflicts_top_n: 8        # max conflicts surfaced; default 8
```

**Ordering.** Critical → high → medium → low. The most severe rule appears
first regardless of which file triggered it.

**Where it sits in CLAUDE.md.** Immediately after the Project section and
*before* the Rules section. Visibility matters: a conflict you'd notice
*after* reading 800 lines of rules is a conflict you don't notice.

---

## Rule Lifecycle (Module 2)

**What it is.** Every graduated rule now carries:

- `graduated_at` — ISO timestamp of graduation (auto-set on `write()`)
- `review_after` — ISO date when the rule should be re-reviewed
  (default: `graduated_at + 180 days`)
- `last_reviewed_at` — ISO timestamp of the last re-rationale
- `expired_at` — ISO timestamp set when the rule moves to `expired/`

Stored as a `<!-- dotagent-meta: ... -->` comment in the rule's markdown.
Round-tripped through `SemanticMemory.read()` / `.write()`.

### Commands

```bash
dotagent dream review-stale
```

Lists every rule that is **overdue for review** (`review_after` in the past),
**due soon** (within the next 14 days by default), **whose cited files have
churned** since graduation, or that is a **legacy rule** with no metadata
and a file mtime > 180 days old.

```bash
dotagent dream rerationale <rule-id> --rationale "Still valid: same auth flow, same risks"
```

Mark a stale rule as reviewed. **Rationale is mandatory** (same rule as
`dream graduate`). Default extension is +180 days; override with
`--extend-days N`.

```bash
dotagent dream expire-stale [--grace-period-days 30] [--dry-run]
```

Move rules whose `review_after` has been past for more than the grace
period to `.agent/dream/expired/<id>.md`. **Files are moved, never deleted.**
The expired copy carries an `expired_at` stamp and a note explaining how to
revive the rule (copy back to its original path).

### Stale rules warning in CLAUDE.md

When stale rules exist, CLAUDE.md gains a short `## ⚠ Rule lifecycle`
section near the top:

```markdown
## ⚠ Rule lifecycle

- **3 rule(s) overdue for review** — they may no longer reflect the current codebase.
- 2 rule(s) due for review in the next 14 days.

Run `dotagent dream review-stale` for the list;
`dotagent dream rerationale <id> --rationale "..."` to extend each,
`dotagent dream expire-stale` to retire past-grace rules.
```

Section is suppressed entirely when no rules are stale. Like conflict
detection: no noise when there's nothing to say.

### Configuration

```yaml
# .agent/config.yaml
dream:
  # implicit defaults — override via SemanticMemory(...).write(entry, lifetime_days=N)
  # or just edit the meta comment in any rule file by hand.
```

(Programmatic-only for now; YAML knobs land if a real user asks.)

### Backward compatibility

Rules written before Module 2 (no `<!-- dotagent-meta: -->` comment) are
treated as follows:

- `graduated_at` falls back to the file's mtime.
- `review_after` is empty → bucketed as "legacy" and surfaced as stale
  once the file is older than the default 180-day lifetime.

Existing rules continue to work without modification. Re-rationaling a
legacy rule for the first time stamps it with current metadata going
forward.

---

## How they work together

The two features are independent but reinforcing.

- **Conflict detection** catches "you're about to violate a rule" *before*
  the change lands.
- **Rule lifecycle** catches "this rule no longer reflects reality" *during
  regular review*.

Without both, you get either:
- Rules that are obeyed but obsolete (no lifecycle), or
- Rules that drift out of mind because nothing surfaces them (no conflict
  detection).

Together they form the governance loop: rules earn trust by being current
(lifecycle) *and* being enforced visibly (conflict detection).

---

## Recommended cadence

| Frequency | Action |
| --- | --- |
| Every commit | Conflict detection runs automatically — no command needed |
| Weekly | `dotagent dream review-stale` — eyeball anything due soon |
| Monthly | Re-rationale rules whose `review_after` has hit; expire what's past grace |
| Quarterly | `dotagent dream expire-stale` to retire fossils |

Auto-Dream's existing GitHub Action template can drive most of this on a
nightly schedule — see [[Auto-Dream]].

---

## Implementation notes

- **Conflict scanning is O(files × rules)** — cheap; bug-registry and
  anti-pattern indices are already cached at `.agent/.cache/sources.json`,
  and `Context.detect_conflicts()` walks them in one pass per rule kind.
- **Cited-file churn detection** uses the cited file's mtime as a proxy
  with a 7-day buffer (a file modified the same day as the rule's
  graduation doesn't count as drift). This avoids expensive `git log`
  per-file analysis at render time. Coarse but cheap; if it turns out to
  miss too many real-drift cases, swap in a `git log --since=<graduated_at>`
  per file when needed.
- **Meta round-trip via HTML comment** rather than YAML frontmatter so the
  rendered rule still looks like clean markdown when viewed on GitHub.

---

## Next steps the design leaves open

- **Block on conflict.** Today the conflict section is informational. A
  future `dotagent project handoff --strict` could refuse to write the
  handoff if any critical-severity rule is in active conflict, unless
  `--override --rationale "..."` is passed.
- **Decay by frequency.** A rule that's been cited in zero commits over
  the last quarter might be expired sooner than its `review_after`
  suggests. The signal is there in the episodic index; not yet wired.
- **Rule families.** When ten anti-patterns all cite `services/auth/*`,
  surface them as a family ("Auth service hot-spot: review all 10").
  Useful at the team level; over-engineered for solo use.
