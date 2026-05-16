# Getting Started

dotagent is a single binary. You install it once per machine and run
`dotagent init` once per project. That's the whole onboarding.

## 1. Install

```bash
pipx install "git+https://github.com/dilawarabbas1/dotagent"
```

Confirm:

```bash
dotagent --version
# dotagent, version 0.2.0
```

If `pipx` isn't installed: `python3 -m pip install --user pipx && pipx ensurepath`.

## 2. Set your identity (once)

```bash
dotagent identity set --id "$(git config user.email | cut -d@ -f1)" \
                      --name "$(git config user.name)" \
                      --email "$(git config user.email)"
```

This writes `~/.config/dotagent/identity.yaml`. Every project on your
machine uses the same identity. Teammates each set their own.

## 3. Initialize a project

```bash
cd ~/code/your-project
dotagent init               # zero prompts; ~5 seconds
```

What `init` does, in order:

1. **Discovery** — detects languages, frameworks, lint config, CI, existing
   AI-tool configs, Claude-Code-Optimization assets.
2. **Ingest** — if `CLAUDE.md` / `.cursorrules` / etc. already exist, parses
   them and routes H2 sections into `.agent/{style,rules,architecture,patterns,preferences}.md`.
3. **LLM draft** (skip with `--no-llm`) — if `ANTHROPIC_API_KEY` is set,
   drafts the five `.agent/*.md` files from discovery + README.
4. **Identity** — resolves the actor from `~/.config/dotagent/identity.yaml`.
5. **Scaffold** — writes the canonical `.agent/` tree.
6. **Index `docs/`** — parses `docs/bug-registry.md`, `docs/anti-patterns.md`,
   etc. (configurable; see [[Sources and Docs]]).
7. **Render adapters** — generates `CLAUDE.md`, `.cursorrules`,
   `.github/copilot-instructions.md`, `AGENTS.md` from the merged Context.
   **Existing files are backed up to `.agent/.imported/<file>.original`
   before being replaced** (one-time backup; subsequent `sync` runs don't
   re-overwrite the backup).
8. **Install hooks** — git pre-commit / post-commit / prepare-commit-msg, and
   Claude Code `.claude/hooks/post-tool.sh`.

## 4. Self-check

```bash
dotagent doctor
```

Each check reports `ok` / `warn` / `fail` / `info`. Exits nonzero on any
`fail`. Run this first whenever something seems off.

## 5. Inspect what an AI agent will see

```bash
dotagent context                  # summary
dotagent context --format markdown | less   # full body
cat CLAUDE.md | head -80          # the actual file the AI reads
```

## 6. Commit

```bash
git status        # see what dotagent added
git add .agent/ CLAUDE.md .cursorrules .github/copilot-instructions.md \
        AGENTS.md .claude/hooks/post-tool.sh
# (skip files that don't exist; the above lists every possible adapter output)
git commit -m "chore: add dotagent context"
```

You're done. Open the repo in Claude Code (or Cursor, or VS Code with
Copilot) and the AI agent has the full project context.

## 7. Daily flow

```bash
# after editing docs/*.md or .agent/*.md:
dotagent sync                     # regenerate every adapter
dotagent sync --dry-run           # see what would change

# during a coding session:
dotagent context                  # confirm the agent sees current state
dotagent who --file <path>        # who/what touched a file

# weekly:
dotagent dream run --since 30d    # extract patterns
dotagent dream list               # review candidates
```

## Teammate onboarding

After you push the initial commit, each teammate runs:

```bash
pipx install "git+https://github.com/dilawarabbas1/dotagent"
git pull
cd <project>
dotagent identity set --id ... --name ... --email ...
dotagent sync                     # personalizes adapters; installs hooks
```

Now their CLAUDE.md will include *their* personal preferences (from
`.agent/memory/personal/<their-id>/profile.yaml`) — not yours.

## Next

- **[[Architecture]]** — see the full picture
- **[[Sources and Docs]]** — wire your existing `docs/*.md` as the source of truth
- **[[Commands Reference]]** — every CLI command in one place
