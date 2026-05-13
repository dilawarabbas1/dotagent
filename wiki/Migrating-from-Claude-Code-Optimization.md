# Migrating from Claude-Code-Optimization

If your project is built on
[dilawarabbas1/Claude-Code-Optimization](https://github.com/dilawarabbas1/Claude-Code-Optimization)
(CLAUDE.md + `.claude/hooks/*` + `docs/bug-registry.md` etc. + `prompts/*.md`),
dotagent comes with a lossless migrator.

## What "lossless" means here

- **`docs/*.md` is never copied.** It stays as the source of truth.
  dotagent indexes it via `.agent/config.yaml` `sources:`.
- **`prompts/*.md` are imported** as `.agent/skills/imported-<slug>.md`
  with a frontmatter wrapper. Originals stay untouched.
- **Existing `CLAUDE.md` content is parsed** and routed into
  `.agent/{style,rules,architecture,patterns,preferences}.md` so your
  hand-written copy survives.
- **`.claude/hooks/*` are preserved.** dotagent's own
  `.claude/hooks/post-tool.sh` is added alongside; existing hooks keep
  running.
- **Pre-existing `CLAUDE.md` is also backed up** to
  `.agent/.imported/CLAUDE.md.original` (one-time) before being replaced
  by dotagent's generated version. Restore with
  `dotagent restore-original` if needed.

## Running the migration

```bash
cd ~/code/your-cco-project
pipx install "git+https://github.com/dilawarabbas1/dotagent"

dotagent init --no-llm        # scaffold .agent/ alongside existing docs/
dotagent migrate-cco          # wire docs/ as sources + import prompts/
dotagent sync                 # render adapters with everything

dotagent doctor               # confirm everything's wired
```

## What `migrate-cco` does step by step

1. **References `docs/*.md` as sources.** Updates `.agent/config.yaml`
   `sources:` block to point at every file from the CCO layout that exists:

   ```yaml
   sources:
     bug_registry:   docs/bug-registry.md      # if exists
     anti_patterns:  docs/anti-patterns.md     # if exists
     redis_keys:     docs/redis-key-registry.md # if exists
     db_impact_map:  docs/db-impact-map.md     # if exists
     dependency_map: docs/dependency-map.md    # if exists
     architecture:   docs/architecture.md      # if exists
   ```

2. **Imports `prompts/*.md` as skills.** For every file in `prompts/`:

   ```
   prompts/deep-debug.md
       → .agent/skills/imported-deep-debug.md  (with frontmatter wrapper)
   ```

3. **Ingests existing `CLAUDE.md` / `.cursorrules` / `.github/copilot-instructions.md` / `AGENTS.md`.**
   Each H2 is routed by keyword:

   | H2 contains      | Routed to                  |
   |------------------|----------------------------|
   | rule / constraint / must / do not | `.agent/rules.md` |
   | style / coding style              | `.agent/style.md` |
   | architecture / system / components / services | `.agent/architecture.md` |
   | pattern / convention              | `.agent/patterns.md` |
   | preference / personal             | `.agent/preferences.md` |
   | (anything else)                   | "Legacy notes" inside `.agent/architecture.md` |

   This preserves your hand-written copy; nothing is dropped.

## Dry-run first

```bash
dotagent migrate-cco --dry-run    # reports what WOULD change
```

Output:

```
referenced sources (5):
  · docs/bug-registry.md
  · docs/anti-patterns.md
  · ...

imported skills (3):
  · imported-deep-debug.md
  · imported-bug-hunt.md
  · ...

ingested buckets (3): style, rules, architecture

note: docs/ kept as the single source of truth. dotagent indexes via
config.yaml `sources:`; no files are duplicated.

[dry-run] nothing was written.
```

## After migration: what changes for your team

| Before (CCO) | After (dotagent) |
|---|---|
| Edit `CLAUDE.md` directly | Edit `docs/*.md` (or `.agent/*.md` for project-wide) → `dotagent sync` |
| Per-tool config maintained manually | Single source generates CLAUDE.md / .cursorrules / .github/copilot-instructions.md / AGENTS.md |
| Bugs in `docs/bug-registry.md` invisible to AI | Top-N bugs (severity-ranked) embedded in every adapter output |
| Prompts in `prompts/` invoked manually | `dotagent skill run <name>` (or pipeline) |
| Hooks in `.claude/hooks/` only | Same hooks + episodic memory + visibility commands |

## After migration: what stays the same

- Your `docs/*.md` are untouched.
- `.claude/hooks/*` keep running (dotagent adds alongside, doesn't replace).
- `prompts/*.md` are still in `prompts/` — imported skills reference them.
- Your existing CLAUDE.md content lives on inside `.agent/*.md`.

## Recovering if something looks wrong

```bash
dotagent doctor                      # diagnose
dotagent context --format markdown   # see the rendered context

# original CLAUDE.md backed up at:
ls .agent/.imported/

# restore the original if you don't like the regenerated version:
dotagent restore-original --name claude

# or all backed-up adapters:
dotagent restore-original
```

If you want to *un-do* dotagent entirely:

```bash
dotagent restore-original            # put back CLAUDE.md / .cursorrules / etc.
rm -rf .agent/                       # remove dotagent state
# manually remove hooks if you want: .git/hooks/{pre-commit,post-commit,prepare-commit-msg}
# and .claude/hooks/post-tool.sh
```

## Common migrator questions

### "Will the migrator clobber my hand-edits to CLAUDE.md?"

No — content is preserved by being ingested into `.agent/*.md` first, then
the original `CLAUDE.md` is backed up to `.agent/.imported/CLAUDE.md.original`,
and a new CLAUDE.md is rendered that includes those ingested sections.

### "What if my `docs/*.md` use a different format than the parsers expect?"

The parsers are tolerant — they'll still extract whatever H2 sections + body
they can. Check the result with `dotagent context --format markdown` and
either reshape your doc slightly, or open an issue to add a kinder parser
variant.

### "Can I run `migrate-cco` twice?"

Yes. It's idempotent — already-referenced sources stay, already-imported
prompts are skipped (existing target files aren't overwritten).

## Next

- **[[Getting Started]]** — full new-project flow
- **[[Sources and Docs]]** — how indexing works after migration
- **[[Troubleshooting]]** — what `dotagent doctor` checks
