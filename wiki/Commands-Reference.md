# Commands Reference

Every dotagent CLI command in one place. `dotagent --help` shows the
top-level list; this page goes deeper.

## Core

### `dotagent init [options]`
One-shot project setup. Zero prompts by default.

| Option | Default | Description |
|--------|---------|-------------|
| `--interactive` | false | Run the question-driven flow |
| `--no-llm` | false | Skip LLM drafting (use scaffold defaults) |
| `--no-hooks` | false | Skip installing git hooks |
| `--no-ingest` | false | Skip parsing existing CLAUDE.md / .cursorrules / etc. |
| `--dry-run` | false | Stop after discovery, write nothing |

### `dotagent sync [options]`
Re-index docs/, rebuild context, regenerate every adapter.

| Option | Description |
|--------|-------------|
| `--no-hooks` | Skip re-installing git hooks |
| `--no-reindex` | Use cached entries (skip docs/ re-parse) |
| `--dry-run` | Show unified diff vs on-disk; write nothing |

### `dotagent status`
Compact summary: identity, adapters, indexed sources, memory counts, active sessions.

### `dotagent doctor [--format text|json]`
Self-check for common misconfigurations. Exits nonzero on `fail`.

### `dotagent context [--format summary|markdown|json]`
Print the merged Context an AI agent sees. `--format markdown` is the full
body that ends up in CLAUDE.md; `--format json` is for tooling.

### `dotagent observe <kind> [options]`
Append an event to episodic memory + update working memory. Used by hooks.

| Option | Description |
|--------|-------------|
| `--tool` | AI tool driving the event (default: `cli`) |
| `--summary` | One-line description |
| `--files` | Newline- or comma-separated file list |
| `--sha` | Commit SHA, if applicable |
| `--session` | Session id (auto-generated if blank) |

### `dotagent reindex [--embed-full-docs]`
Re-parse every configured source under `docs/`. Updates cache + pointer cards.

### `dotagent reindex-events`
Rebuild the SQLite event index from JSONL. Run if `who`/`activity`/etc.
seem stale or empty.

### `dotagent trailer`
Print the dotagent attribution trailer (used by `prepare-commit-msg` hook).

### `dotagent migrate-cco [--dry-run]`
Lossless Claude-Code-Optimization migrator. See
[[Migrating from Claude-Code-Optimization]].

### `dotagent restore-original [--name claude|cursor|copilot|opencode] [--list]`
Restore a pre-dotagent AI-tool config from its `.agent/.imported/` backup.

## Identity

### `dotagent identity show`
Print the active actor (resolved from `~/.config/dotagent/identity.yaml` →
git config → OS user).

### `dotagent identity set [options]`
Save your identity globally to `~/.config/dotagent/identity.yaml`.

| Option | Description |
|--------|-------------|
| `--id` | Slug used as actor id (default: derived from email) |
| `--name` | Display name |
| `--email` | Add to emails list |
| `--github` | GitHub handle |
| `--gitlab` | GitLab handle |
| `--default-tool` | claude_code / cursor / copilot / opencode |
| `--role` | contributor / lead / etc. |

## Visibility (Phase 2)

### `dotagent who --file <path> | --rule <slug>`
Who touched a file (or worked on a rule) and with which AI tool.

### `dotagent activity [options]`
Filtered event feed.

| Option | Default | Description |
|--------|---------|-------------|
| `--since` | `7d` | Lookback window: `7d` / `24h` / `30m` / ISO datetime |
| `--by` | (any) | Filter by actor id |
| `--tool` | (any) | Filter by AI tool |
| `--kind` | (any) | Filter by event kind |
| `--limit` | 50 | Max rows |

### `dotagent timeline <path> [--limit N]`
Per-file edit timeline, newest first.

### `dotagent feed [--limit N]`
Chronological team-wide event stream.

### `dotagent leaderboard [--since 30d]`
Per-actor activity counts: events / commits / graduations.

## Skills (Phase 3)

### `dotagent skill list`
List every skill found in `.agent/skills/*.md`.

### `dotagent skill show <name> [--task ...]`
Print the resolved system + user prompts for a skill. No LLM call.

### `dotagent skill run <name> [--task ...] [--dry-run] [--format text|json]`
Run a skill. Without `ANTHROPIC_API_KEY` set, returns the resolved prompt.

### `dotagent skill pipeline <names...> [--task ...] [--dry-run]`
Chain skills — each output becomes the next's `prior_output`.

## Tools (Phase 4)

### `dotagent tool list`
List the four built-in tools.

### `dotagent tool pattern-extractor [--write]`
Run Python AST + JS/TS import scan. `--write` emits semantic-pattern entries.

### `dotagent tool memory [<query>] [--summary]`
Search across episodic / semantic / sources / personal. `--summary` for
store-level counts.

### `dotagent tool debug <trace> | --file <path> | --file -`
Match a stack trace against episodic memory + bug-registry.

### `dotagent tool checklist [--since 14d] [--format text|json]`
Synthesize a pre-deploy gate from rules.md + bug-registry + recent
reverts/fixes.

## Auto-Dream (Phase 5)

### `dotagent dream run [options]`
Extract signals from episodic memory, write candidates.

| Option | Default | Description |
|--------|---------|-------------|
| `--since` | `30d` | Lookback window |
| `--min-cluster-size` | 3 | Min events to form a signal |
| `--no-embeddings` | false | Disable embedding clusters even if `[ml]` installed |
| `--quiet` | false | Suppress per-signal output |

### `dotagent dream list`
List pending candidates awaiting review.

### `dotagent dream graduate <id> --rationale "..."`
Promote a candidate to a graduated semantic rule. **Rationale is mandatory.**

### `dotagent dream reject <id> --rationale "..."`
Reject a candidate. **Rationale is mandatory.**

### `dotagent dream cron-install [--schedule "0 2 * * *"]`
Install a per-repo crontab entry.

### `dotagent dream cron-uninstall`
Remove the dotagent dream cron entry for this repo.

### `dotagent dream github-action`
Write a `.github/workflows/dotagent-dream.yml` template.

## Bridges

### `dotagent watch cursor`
Foreground file-watcher for Cursor < 0.40. Requires `pip install 'dotagent[watch]'`.

### `dotagent serve [options]`
Run the centralized event server. Requires `pip install 'dotagent[server]'`.

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `9700` | Bind port |
| `--db` | `~/.local/share/dotagent/server.sqlite` | SQLite path |
| `--bootstrap-admin-token` | (auto) | Pre-seed an admin token |

## Environment variables

| Var | Purpose |
|-----|---------|
| `ANTHROPIC_API_KEY` | LLM-backed drafting + `skill run` |
| `DOTAGENT_DEBUG=1` | Surface silenced exceptions to stderr |
| `XDG_CONFIG_HOME` | Override `~/.config` location for `identity.yaml` |
