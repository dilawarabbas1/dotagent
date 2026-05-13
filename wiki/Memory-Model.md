# Memory Model

dotagent implements four distinct kinds of memory, drawn from
cognitive-science models. Each has a different scope, lifecycle, and
sharing policy.

## Working memory — *what's happening now*

**Path:** `.agent/memory/working/<actor>/current.json`
**Updated by:** every `dotagent observe` call (git hooks + Claude Code post-tool)
**Shared:** local only

Holds the live session state: session id, AI tool currently driving the
work, branch, current task (if set via `dotagent observe task-start`),
recent files, and last N events. Every AI agent that reads CLAUDE.md sees
this rolled into a "what's happening now" section.

```json
{
  "actor": "alice",
  "session": "e7dcdce90f1c",
  "tool": "claude_code",
  "branch": "feat/jwt-rotation",
  "started_at": "2026-05-06T10:00:00Z",
  "updated_at": "2026-05-06T10:42:18Z",
  "recent_files": ["services/auth/jwt.py", "tests/test_jwt.py", ...],
  "recent_events": [{"ts": ..., "kind": "edit", "tool": "claude_code", "summary": ...}, ...],
  "task": "ship JWT rotation fix"
}
```

## Episodic memory — *what happened before*

**Path:** `.agent/memory/episodic/YYYY/MM/DD/<actor>__<session>.jsonl`
**Index:** `.agent/memory/episodic/index.sqlite` (gitignored, rebuildable)
**Updated by:** every `dotagent observe` call
**Shared:** committed, attributable

Append-only JSONL log. One file per actor per session per day. This is
**the design that makes multi-developer safe**: two teammates writing to
the same file on the same day produce distinct files (different `actor`,
different `session`), so git never sees a conflict.

Each line is a structured event:

```json
{"ts":"...","actor":"alice","tool":"claude_code","host":"laptop",
 "session":"abc","kind":"edit","repo":"my-app","branch":"main",
 "files":["src/x.py"],"diff_sha":"","summary":"refactored handler"}
```

The SQLite index (`index.sqlite`) is built from JSONL on demand and powers
fast queries: `who`, `activity`, `timeline`, `feed`, `leaderboard`. If it
gets corrupted, run `dotagent reindex-events` to rebuild from JSONL.

## Semantic memory — *patterns and rules*

**Paths:**
- `.agent/memory/semantic/rules/<category>/<sha>-<slug>.md`
- `.agent/memory/semantic/patterns/<category>/<sha>-<slug>.md`
- `.agent/memory/semantic/sources/<id>.md` ← pointer cards for indexed `docs/`

**Updated by:** Auto-Dream graduations, `dotagent tool pattern-extractor --write`, reindex
**Shared:** committed

Two flavors:

1. **Graduated entries** — rules that came out of Auto-Dream review. Every
   one has `## Rationale`, `## Evidence`, `## Provenance`, `## Graduated by`
   sections. This is the audit trail of what the agent has learned.
2. **Source pointer cards** — one per indexed `docs/*.md`. Lightweight (no
   content duplication), just: source path + summary + last-indexed
   timestamp. Tells the AI "the canonical version of this knowledge lives
   at `docs/bug-registry.md`".

Slugs are SHA1-prefixed (`<8-char-sha>-<slugified-title>.md`) so two
teammates writing similar entries never collide.

## Personal memory — *style and preferences*

**Path:** `.agent/memory/personal/<actor>/profile.yaml`
**Updated by:** manual edit; Auto-Dream personal graduations
**Shared:** **never merged into other actors' adapter outputs**

Per-actor profile. When dotagent renders CLAUDE.md on Alice's machine,
*Alice's* preferences appear; Bob's CLAUDE.md (on Bob's machine) shows
*Bob's*. Even though both are derived from the same git history.

```yaml
# .agent/memory/personal/alice/profile.yaml
editor: vim
favorite_lang: python
preferences:
  - prefer pytest over unittest
  - use type annotations everywhere
  - avoid emoji in commit messages
```

The personal section appears in CLAUDE.md as:

```markdown
## Personal preferences for `alice`
- editor: vim
- favorite_lang: python
- preferences: prefer pytest over unittest, use type annotations everywhere, avoid emoji in commit messages
```

This file is committed to git, but adapter rendering filters by actor so
Bob never sees Alice's preferences in his generated CLAUDE.md.

## How adapters use the four memories

When the adapter renders CLAUDE.md, it calls `dotagent.context.build()` which
loads all four memories plus indexed sources plus the five `.agent/*.md`
files. The renderer then surfaces:

| Section in CLAUDE.md           | Source                                              |
|--------------------------------|------------------------------------------------------|
| "Working memory — what's happening now" | Working memory current.json                  |
| "Recent activity (episodic memory)" | Last N episodic events filtered to recent files |
| "Patterns (graduated knowledge)" | Semantic memory (and `.agent/patterns.md`)         |
| "Personal preferences for `<actor>`" | Personal memory profile.yaml                   |
| "Bug registry — known bugs to avoid" | Indexed `docs/bug-registry.md` via semantic pointer card |
| "Anti-patterns — do not introduce these" | Indexed `docs/anti-patterns.md`                |
| etc.                           |                                                      |

## When you should care which memory is which

- **Editing project rules** → `.agent/rules.md` (or `docs/` if you want to
  use the source-of-truth pattern). Flows into "Rules" section.
- **Recording an experience to look back on** → it happens automatically via
  hooks (episodic). You don't write episodic memory by hand.
- **Graduating an observation into a permanent rule** → use
  `dotagent dream graduate <id> --rationale "..."`. Rationale is mandatory.
- **Setting your personal style** → edit
  `.agent/memory/personal/<your-id>/profile.yaml` directly.

## Next

- **[[Auto-Dream]]** — how episodic experience becomes graduated semantic rules
- **[[Multi-Project and Multi-Developer]]** — keeping memory isolated and attributable
