# FAQ

## What's the one-line pitch?

"One source of truth for every AI coding tool, with built-in multi-developer
attribution and a learning loop."

## How does this differ from CLAUDE.md / .cursorrules / Copilot custom instructions?

Those are *output formats*. dotagent is the *system* that generates all of
them (and keeps them in sync) from a single source — your `docs/*.md` plus
the four memories.

## Do I need an API key?

No. dotagent works without `ANTHROPIC_API_KEY`. The key enables two
features:

1. LLM-backed drafting of `.agent/*.md` on `dotagent init`.
2. `dotagent skill run` execution (without the key, returns the resolved prompt).

Everything else works offline.

## Does dotagent send my code anywhere?

No. The base install does not phone home. The optional `dotagent server`
is software *you* run on *your* infrastructure; clients only post to it
when you explicitly set `server.forward_events: true`.

The optional `[ml]` extra downloads the `all-MiniLM-L6-v2` sentence
transformer (~22MB) from HuggingFace the first time you use embeddings.

## Will dotagent overwrite my existing CLAUDE.md?

Yes — but **content is preserved**:

1. On `init`, your existing CLAUDE.md is parsed (the "ingest" phase) and
   its H2 sections are routed into `.agent/{style,rules,architecture,patterns,preferences}.md`.
2. The original file is backed up to `.agent/.imported/CLAUDE.md.original`
   (one-time, never re-overwritten).
3. A new CLAUDE.md is rendered that **includes** the contents of those
   `.agent/*.md` files.

If you decide you don't want dotagent managing CLAUDE.md, restore the
original with `dotagent restore-original --name claude`.

## What if I want completely different rules for AI assistants in dev vs prod?

dotagent doesn't directly model dev/prod. Workarounds:

- Use two repos (different `.agent/`).
- Use environment-specific `docs/*-dev.md` and `docs/*-prod.md`, switch
  `.agent/config.yaml` `sources:` via a script.
- Use the custom adapter to render two different output files.

## Can two teammates work on the same file at the same time?

Yes. Episodic JSONL filenames namespace by `<actor>__<session>`, so two
people writing on the same day produce different files. Git merges
trivially. The semantic memory uses content-hashed slugs, so two graduations
of similar rules don't collide either.

## What about my personal style — is it shared with teammates?

No. `.agent/memory/personal/<actor>/profile.yaml` is per-actor. On *your*
machine, your CLAUDE.md contains your preferences. On your teammate's
machine, their CLAUDE.md contains *their* preferences. Even though both
files are committed to the same git repo.

## Why is `prepare-commit-msg` the trailer hook?

Because it's the only commit-time hook that runs *before* the commit
object is finalized, so the trailer becomes part of the actual commit
message (visible in `git log` forever). Post-commit hooks can't modify
the commit; pre-commit hooks run before the message is written.

## Can I disable some adapters?

Yes. In `.agent/config.yaml`:

```yaml
adapters:
  claude: true
  cursor: false       # don't generate .cursorrules
  copilot: false      # don't generate .github/copilot-instructions.md
  opencode: false
```

`dotagent sync` then only writes CLAUDE.md.

## How big is the install?

- Base: ~5 MB (click, PyYAML, Jinja2, anthropic SDK).
- `[ml]` extra: ~120 MB (sentence-transformers + sklearn + numpy) +
  ~22 MB model on first use.
- `[server]` extra: ~30 MB (fastapi + uvicorn + starlette).
- `[watch]` extra: ~1 MB (watchdog).

## Does dotagent work on Windows?

The Python parts do (Python 3.11+). The Cursor watcher uses `pgrep` which
isn't standard on Windows — file detection still works, but the
"is-Cursor-running" gate won't. Shell hooks are bash; on Windows use Git
Bash or WSL.

## Can dotagent itself use dotagent?

Yes. The dotagent repo is in fact set up as a dotagent project — see its
own `.agent/` and `CLAUDE.md`. Useful for dogfooding.

## Is there an exit strategy?

```bash
dotagent restore-original    # put back any backed-up AI configs
rm -rf .agent/               # remove all dotagent state
# manually remove hooks if you want:
rm -f .git/hooks/{pre-commit,post-commit,prepare-commit-msg}
rm -f .claude/hooks/post-tool.sh
```

Your `docs/*.md` are untouched — they were never managed by dotagent.

## Why is the Auto-Dream rationale mandatory?

Because a graduated rule shapes every future AI coding session on every
teammate's machine. Six months from now, when someone asks "why does the
agent always X?", the rationale file is the answer. Without it, you have
rules with no audit trail and no one can decide whether to keep, change,
or retire them.

## How do I know what an AI agent will actually read?

```bash
dotagent context                  # summary
dotagent context --format markdown   # exactly what's rendered
cat CLAUDE.md                     # exactly what Claude Code reads
```

## Where can I see the source?

[github.com/dilawarabbas1/dotagent](https://github.com/dilawarabbas1/dotagent)

## I have a question that isn't here

Open an issue: [github.com/dilawarabbas1/dotagent/issues](https://github.com/dilawarabbas1/dotagent/issues).
Include the output of `dotagent doctor --format json`.
