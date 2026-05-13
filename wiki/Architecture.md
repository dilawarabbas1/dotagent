# Architecture

dotagent is a **context resolver** that merges six inputs into one structured
object that every AI tool can read.

## The diagram

```
docs/*.md  ─────────────────────┐
(your hand-written truth)       │
                                ▼
            ┌─────────────────────────────────┐
            │   Source Indexer (sources.py)   │
            │   bug-registry, anti-patterns,  │
            │   redis-keys, db-impact-map,    │
            │   dependency-map, architecture  │
            └─────────────┬───────────────────┘
                          │ structured entries
                          ▼
.agent/*.md ──┐  ┌───────────────────┐  ┌── memory/working   (now)
              ├─▶│  Context Resolver │◀─┼── memory/episodic  (before)
config.yaml ──┘  │   (context.py)    │  ├── memory/semantic  (patterns + indexed sources)
                 └─────────┬─────────┘  └── memory/personal  (per-actor)
                           │ merged Context object
                           ▼
                ┌──────────────────────┐
                │  Adapters (render)   │
                │  CLAUDE.md, .cursor- │
                │  rules, copilot, ...  │
                └──────────┬───────────┘
                           ▼
       AI agent reads CLAUDE.md and gets:
       · project rules + indexed bug-registry highlights
       · anti-patterns to avoid
       · DB tables & redis keys to be careful with
       · dependency map (which services touch what)
       · personal style for the current actor
       · recent activity on currently-touched files
       · pointers back to docs/*.md for full content
```

## The six inputs

1. **`docs/*.md`** — Your hand-written canonical knowledge. dotagent never
   writes here. It indexes via `.agent/config.yaml` `sources:` block. See
   [[Sources and Docs]].
2. **`.agent/*.md`** — Five project-wide source files
   (style / rules / architecture / patterns / preferences) that supplement
   `docs/`.
3. **Working memory** — Per-actor `current.json` tracking the live session
   (branch, recent files, recent events, current task). Local only.
4. **Episodic memory** — Append-only JSONL log of every event. Partitioned
   by date + actor + session so concurrent writes never conflict. Committed.
5. **Semantic memory** — Graduated patterns/rules + pointer cards for
   indexed sources. Committed (content-hashed slugs).
6. **Personal memory** — Per-actor preferences profile. Never merged into
   other actors' generated outputs.

## The Context resolver

`dotagent.context.build(paths, actor, config)` loads all six inputs and
returns a single `Context` dataclass. The adapters (Claude / Cursor / Copilot
/ OpenCode / Custom) all render from this same object — so every AI tool
sees the same context, just packaged for its file format.

Key methods on `Context`:

- `ctx.top_bugs(n)` — top-N bugs ranked by severity from `docs/bug-registry.md`
- `ctx.top_anti_patterns(n)`
- `ctx.redis_keys()`, `ctx.db_impact()`, `ctx.dependency_map()`,
  `ctx.architecture_sections()`
- `ctx.hotspots_for_files(files)` — for a list of files, return matching
  bugs/anti-patterns/tables/keys

## What lives where

```
your-repo/
├── docs/                         ← YOU edit. dotagent reads.
│   ├── bug-registry.md
│   ├── anti-patterns.md
│   ├── redis-key-registry.md
│   ├── db-impact-map.md
│   ├── dependency-map.md
│   └── architecture.md
├── CLAUDE.md                     ← generated. don't hand-edit.
├── .cursorrules                  ← generated.
├── .github/copilot-instructions.md  ← generated.
├── AGENTS.md                     ← generated.
└── .agent/                       ← dotagent manages
    ├── config.yaml               ← Config (incl. sources:)
    ├── style.md rules.md ...     ← five project-wide source files
    ├── identity/
    │   ├── developers.yaml       ← roster
    │   └── tools.yaml
    ├── memory/
    │   ├── working/<actor>/current.json
    │   ├── episodic/YYYY/MM/DD/<actor>__<session>.jsonl
    │   ├── episodic/index.sqlite       ← gitignored, rebuilt from JSONL
    │   ├── semantic/{patterns,rules}/<category>/<sha>-<slug>.md
    │   ├── semantic/sources/<id>.md    ← pointer cards
    │   └── personal/<actor>/profile.yaml   ← never merged
    ├── dream/{candidates,graduated,rejected}/
    ├── skills/                   ← prompts the skill runtime uses
    ├── tools/                    ← tool contracts
    ├── adapters/custom/          ← user-defined Jinja templates
    ├── .imported/                ← one-time backups of pre-existing AI configs
    └── .cache/                   ← gitignored; sources cache + others
```

## Hooks

- **`.git/hooks/pre-commit`** → `dotagent observe pre-commit --files <staged>`
- **`.git/hooks/post-commit`** → `dotagent observe post-commit --sha <HEAD>`
- **`.git/hooks/prepare-commit-msg`** → appends a `Co-authored-by: dotagent ...`
  trailer with actor + tool so attribution survives in `git log` even on
  machines without dotagent.
- **`.claude/hooks/post-tool.sh`** → `dotagent observe post-tool --tool claude_code`
  fires after every Claude Code Edit/Write/Bash.

## Multi-developer invariants (locked design decisions)

- **Episodic JSONL filenames** are `<actor>__<session>.jsonl`, partitioned by
  date directory → **zero merge conflicts**.
- **Semantic entries** use SHA1-prefixed slugs → **zero collisions across
  teammates**.
- **Personal memory** lives at `memory/personal/<actor>/` and is **never
  merged** into other actors' adapter outputs. Your CLAUDE.md contains
  *your* personal preferences; your teammate's CLAUDE.md contains *theirs*.

## Next

- **[[Memory Model]]** — deep dive on the four memories
- **[[Sources and Docs]]** — how `docs/` indexing works
- **[[Configuration Reference]]** — every key in `.agent/config.yaml`
