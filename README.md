# dotagent

Tool-agnostic AI coding context manager. One `.agent/` folder, every AI coding tool in sync.

Manages a single source of truth (`.agent/`) and generates the right config for Claude Code, Cursor, GitHub Copilot, OpenCode, and custom tools — so your project's coding rules, architecture, patterns, and team memory follow you everywhere.

## Quickstart (plug-and-play)

```bash
pipx install dotagent

cd ~/code/your-repo
dotagent init       # zero-prompt: scans, drafts, scaffolds .agent/, generates adapters, installs hooks
git add .agent/ CLAUDE.md .cursorrules .github/copilot-instructions.md AGENTS.md
git commit -m "chore: add dotagent context"
git push
```

**Teammates** (each, once):

```bash
pipx install dotagent
git pull
dotagent sync       # rebuilds adapters locally + installs hooks; identity comes from `git config user.email`
```

That's the entire onboarding.

## What's in `.agent/`

| Path | Purpose |
| --- | --- |
| `style.md` `rules.md` `architecture.md` `patterns.md` `preferences.md` | Source markdown — edit, run `dotagent sync`, all adapters update. |
| `identity/developers.yaml`        | Roster of developers (id, emails, default tool). |
| `memory/working/<actor>/`         | Session state (local). |
| `memory/episodic/`                | Append-only event log per actor — committed, attributable. |
| `memory/semantic/`                | Graduated patterns + rules — the team's permanent learning. |
| `memory/personal/<actor>/`        | Per-developer style + vetoes — never sent into other people's adapters. |
| `dream/`                          | Auto-Dream candidates / graduated / rejected — every decision carries a written rationale. |
| `adapters/`                       | Generated tool configs (don't hand-edit). |
| `skills/` `tools/`                | Built-in skill prompts and tool contracts. |

## Built-in commands (Phase 1)

```
dotagent init             # one-shot setup; --interactive for the question flow
dotagent sync             # regenerate adapters + install hooks
dotagent identity show    # who am I
dotagent identity set     # save your identity globally
dotagent observe <kind>   # append an event (used by hooks)
dotagent status           # summary
```

Phase 2+: `dotagent skill run`, `dotagent dream`, `dotagent who`, `dotagent activity`, `dotagent leaderboard`, `dotagent timeline`.

## Multi-developer + multi-AI-tool tracking

Every event records `actor` (the human, resolved from `git config user.email` via the alias map in `identity/developers.yaml`) and `tool` (the AI platform driving the work — `claude_code | cursor | copilot | opencode | custom | cli`). Episodic JSONL files use `<actor>__<session>.jsonl` filenames so merges never conflict. Semantic memory files use content-hashed slugs so collisions are impossible. Personal memory is per-actor and never merged.

Git Proxy adds a `Co-authored-by: dotagent <tool=claude_code,actor=alice>` trailer on commits so attribution survives in `git log` even without `dotagent` installed.

## License

MIT
