# Sources and Docs

The key innovation: **`docs/*.md` is the source of truth.** dotagent reads
it but never writes there. Edit one file in `docs/`, run `dotagent sync`,
every AI tool on every developer's machine picks up the change.

## Configuration

`.agent/config.yaml` `sources:` block points dotagent at your `docs/` files.
Defaults:

```yaml
sources:
  bug_registry:   docs/bug-registry.md
  anti_patterns:  docs/anti-patterns.md
  redis_keys:     docs/redis-key-registry.md
  db_impact_map:  docs/db-impact-map.md
  dependency_map: docs/dependency-map.md
  architecture:   docs/architecture.md
  extra: []        # see below
```

Missing files are tolerated — they just won't appear in CLAUDE.md. Run
`dotagent doctor` to see which configured sources exist on disk.

## Built-in source kinds and their parsers

Each kind has a dedicated parser. All parsers are tolerant: they extract H2
sections + bulleted metadata, and fall back to capturing raw section bodies
when the format isn't recognized.

### `bug_registry`

```markdown
## BUG-007: Stale JWT cache accepts revoked tokens
- **Severity**: critical
- **Files**: services/auth/jwt.py, services/cache/redis.js
- **Component**: auth-service

Body text describing the bug.
```

Extracts: `id`, `title`, `severity`, `files`, `components`, `tags`, full body.
Ranks by severity (critical → high → medium → low) when rendering.

### `anti_patterns`

Same shape as bug_registry. Sections are H2 with optional `ID: title` prefix.

### `redis_keys`

```markdown
## RED-001: Session cache
- **Service**: auth-service
- **Keys**: `session:{user_id}`, `session:meta:{user_id}`

Body. Backticked key patterns in the body are also extracted.
```

Extracts: keys (from `**Keys:**` metadata OR backtick-wrapped patterns in
the body), services, body.

### `db_impact_map`

```markdown
## DB-001: Users + audit_log
- **Tables**: users, audit_log
- **Files**: services/users/repo.py
```

Extracts: table names (from `**Tables:**` metadata OR `table.column`
references in the body), files, components.

### `dependency_map`

```markdown
## DEP-001: Auth flow
- **Services**: api-gateway, auth-service, users-service

Body. Bullets containing → arrows are also parsed as deps.
```

Extracts: components/services (from metadata OR arrow notation in bullets).

### `architecture`

H2-delimited. Each section becomes a SourceEntry. Used to give the AI
agent a section index and pointer to the full doc.

### `generic`

Default. Any source kind not in the list above is parsed generically: each
H2 becomes an entry with title + body. Useful for `sources.extra`.

## Extra sources

Add arbitrary docs via `sources.extra`:

```yaml
sources:
  bug_registry: docs/bug-registry.md
  # ... other defaults ...
  extra:
    - name: api_contracts
      path: docs/api/contracts.md
      kind: generic
    - name: oncall_runbook
      path: docs/runbooks/oncall.md
      kind: generic
```

These get indexed and rendered as additional sections in CLAUDE.md.

## What gets surfaced in CLAUDE.md

After running `dotagent sync` you'll see (for each non-empty source):

```markdown
## Bug registry — known bugs to avoid

_Source of truth: `docs/bug-registry.md` (12 bugs (3 critical, 5 high, 4 medium)). Top 15 shown; full list in source._

### BUG-007 [critical] — Stale JWT cache accepts revoked tokens
- Files: `services/auth/jwt.py`, `services/cache/redis.js`
- Components: `auth-service`

Body excerpt.
```

The footer of CLAUDE.md lists every indexed source with its path, so the
AI agent can fetch the full file when the embedded summary isn't enough.

## How many entries are included?

`.agent/config.yaml` `context:` block:

```yaml
context:
  bug_registry_top_n: 15      # top-N by severity
  anti_patterns_top_n: 10
  recent_activity_top_n: 8    # last N episodic events
  embed_full_docs: false      # also cache full doc text (rarely needed)
```

The rest stays in your `docs/` file — the AI fetches it on demand by
following the source-pointer footer.

## When does indexing happen?

| Trigger | Action |
|---------|--------|
| `dotagent init` | Indexes all sources, writes cache + pointer cards. |
| `dotagent sync` | Re-indexes (skip with `--no-reindex`). |
| `dotagent reindex` | Explicit re-index, no adapter render. |
| `dotagent observe` is fired on a file under `docs/*.md` | Auto-reindexes (so the next sync picks up your edit). |

## Where the parsed entries are stored

Two places:

1. **`.agent/.cache/sources.json`** — gitignored. Full structured cache.
   Regenerated cheaply on demand. Adapters read this on every render.
2. **`.agent/memory/semantic/sources/<name>.md`** — committed. Lightweight
   pointer cards (no content duplication). Tell the AI "the canonical
   version of this knowledge lives at `docs/X.md`."

## Custom parsers

If your `docs/some-thing.md` uses a format the built-in parsers don't
handle well, you have two options:

1. **Refactor the doc** to match the H2-with-metadata convention (most
   tolerant; see [`examples/`](https://github.com/dilawarabbas1/dotagent/tree/main/examples)).
2. **Add a parser** in `src/dotagent/sources.py` and register it in
   `_PARSERS`. See [CONTRIBUTING.md](https://github.com/dilawarabbas1/dotagent/blob/main/CONTRIBUTING.md).

## Example: indexing your own docs

See the `examples/` directory in the repo. After `cd examples && dotagent init`,
inspect the generated `CLAUDE.md` to see exactly how each `docs/*.md` file
turns into a section.

## Next

- **[[Architecture]]** — full system diagram
- **[[Configuration Reference]]** — every key in config.yaml
- **[[Migrating from Claude-Code-Optimization]]** — automated migrator for
  CCO repos
