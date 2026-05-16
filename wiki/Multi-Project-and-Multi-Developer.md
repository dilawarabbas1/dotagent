# Multi-Project and Multi-Developer

dotagent is designed for both axes: one developer with N projects, one
project with N developers, or N × M.

## Per-machine vs per-project

| Layer | Scope | Location |
|-------|-------|----------|
| CLI binary | one-per-machine | `~/.local/bin/dotagent` (via `pipx`) |
| Identity | one-per-machine (one human, every project) | `~/.config/dotagent/identity.yaml` |
| `ANTHROPIC_API_KEY` | shared env var | shell |
| **Everything else** | **per-project** | each repo's `.agent/` |

Install dotagent once. Run `dotagent init` in every project. Each gets
its own isolated `.agent/`.

## Multi-project workflow

```bash
# once on your machine
pipx install "git+https://github.com/dilawarabbas1/dotagent"
dotagent identity set --id dilawar --name "Dilawar Abbas" --email dilawar@eocean.com.pk

# per project — repeat for each
cd ~/code/aigent-portal && dotagent init && dotagent doctor
cd ~/code/aigent-backend && dotagent init && dotagent doctor
cd ~/code/aigent-admin && dotagent init && dotagent doctor

# (optional) one-line health check across all
for r in ~/code/aigent-portal ~/code/aigent-backend ~/code/aigent-admin; do
  echo "=== $r ==="; (cd "$r" && dotagent status)
done
```

Each repo gets:
- its own `.agent/config.yaml` (its own `sources:` pointing at its own `docs/`)
- its own `CLAUDE.md` (rendered from its own context)
- its own episodic JSONL log + SQLite index
- its own `.git/hooks/*` and `.claude/hooks/post-tool.sh`
- its own optional cron entry for auto-dream
- its own (per-actor) personal memory profile

## Multi-developer workflow

After the first dev pushes a dotagent-initialized repo:

```bash
# each teammate, once on their machine
pipx install "git+https://github.com/dilawarabbas1/dotagent"
dotagent identity set --id <slug> --name "Their Name" --email their@email.com

# per project
cd <project>
git pull
dotagent sync        # re-renders CLAUDE.md with THEIR personal preferences,
                     # reinstalls hooks locally
```

That's it. Their next commit auto-attributes correctly:

```
$ git log -1 --format=%B
fix: redact pagination cursor in logs

Co-authored-by: dotagent <dotagent@local> trailer-actor=bob trailer-tool=cursor
```

## What gets isolated between teammates

| What | How |
|------|-----|
| Episodic events | `<actor>__<session>.jsonl` filenames — never collide |
| Semantic entries | SHA1-prefixed slugs — never collide |
| Personal memory | per-actor directory, never merged into other actors' adapter outputs |
| Working memory | local only (never committed) |

## What gets shared between teammates

| What | Why |
|------|-----|
| `.agent/config.yaml` | project-wide config; everyone sees the same sources |
| `.agent/*.md` (style, rules, etc.) | project-wide source files |
| Episodic JSONL | attributable team-wide audit trail |
| Semantic memory | graduated rules apply to everyone |
| `docs/*.md` | the source of truth |
| Generated `CLAUDE.md` (etc.) | committed for read-time bootstrap; regenerated per-machine on `sync` to include personal memory |

Personalization happens **on sync, on each machine**. Alice's CLAUDE.md
contains Alice's preferences; when Bob pulls + syncs, his CLAUDE.md
contains Bob's. The committed CLAUDE.md is just a starting point.

## When working memory is "stale" for teammates

Your working memory `current.json` lives at
`.agent/memory/working/<actor>/current.json`. By design this is **per-actor**,
so Bob's machine never reads Alice's `current.json`. But teammates can see
Alice's recent activity via:

- `dotagent activity --by alice`
- `dotagent who --file <path>`
- `dotagent timeline <path>`

All of which run off the committed episodic JSONL, not Alice's local
working memory.

## With the optional server

If you run `dotagent serve` (see [[Server and RBAC]]), point every repo's
`.agent/config.yaml` `server.url` at it. All events from all repos from
all teammates land in one real-time stream, filterable per repo / per
actor in the dashboard.

```yaml
# in every repo's .agent/config.yaml:
server:
  url: https://dotagent.internal:9700
  token: <writer-token-for-this-actor>
  forward_events: true
```

One `serve` instance per company is plenty.

## Common questions

### "We all have different `.agent/memory/personal/` profiles. Do they conflict in git?"

No. Each actor has their own subdirectory: `.agent/memory/personal/alice/`,
`.agent/memory/personal/bob/`. Two teammates editing their own profiles
never touch the same file.

### "Should I commit `.agent/.cache/`?"

No, it's gitignored (dotagent writes the `.gitignore` for you). Regenerate
on demand.

### "Should I commit `.agent/memory/episodic/index.sqlite`?"

No, it's gitignored. Anyone can `dotagent reindex-events` to rebuild it
from JSONL.

### "Two teammates worked on different machines today and both committed. Will their episodic JSONLs conflict?"

No. Today's filenames are:
- `alice__abc123.jsonl` (her session)
- `bob__def456.jsonl` (his session)

Different filenames; git merges trivially.

### "Can teammates have different `adapters:` settings?"

Yes. `.agent/config.yaml` is shared, but if one teammate doesn't use Cursor,
they can override locally — or just ignore the `.cursorrules` regen since
it won't bother anything. Cleaner: agree as a team which adapters are on.

## Next

- **[[Memory Model]]** — exactly which memory is shared vs per-actor
- **[[Server and RBAC]]** — centralized real-time view
- **[[Auto-Dream]]** — graduations are team-wide; reviewing them is per-PR
