# dotagent — project context

Living context document. Read this before resuming work in a new session. Last updated: 2026-05-05.

## What dotagent is

A tool-agnostic AI coding context manager. One `.agent/` folder is the source of truth; dotagent generates the right config for Claude Code, Cursor, GitHub Copilot, OpenCode, and custom tools from it. Plug-and-play across new and existing projects, multi-developer + multi-AI-tool tracking built in.

It generalizes `dilawarabbas1/Claude-Code-Optimization` (Claude-only framework: CLAUDE.md + 5 hooks + 2 skills + 10 docs + 8 prompts + 6 registries) into a tool-neutral system, while preserving every existing asset via importer.

## Goals (verbatim from user)

- Coding Style, Project Rules, Architecture, Patterns, Preferences (the five `.agent/*.md` source files)
- `.agent/` folder with four memory types: Working Memory (now), Episodic Memory (before), Semantic Memory (patterns & rules), Personal Memory (style & preferences)
- Built-in skills: Observer, Research, Plan, Code, Review
- Tools it should support: Claude Code, Cursor, Copilot, OpenCode (OpenClaw), Custom
- Tools it offers: Git Proxy, Pattern Extractor, Memory Manager, Debug Investigator, Deploy Checklist
- Auto-Dream: cluster agent experiences into recurring patterns; review them; graduate the good ones, reject the bad. Run via CRON. Every graduated/rejected pattern requires a written rationale — that file is the audit of what the agent learned.
- Plug-and-play: two commands install on any repo, new or existing.
- Multi-developer: track who did what across which AI tool; teammates with repo access see the full attributed history.
- Existing project doc structure (`<project>/docs/...`) stays exactly as it is — dotagent indexes it, never duplicates.

## Status — Phase 1 SHIPPED

Plug-and-play install works today. The walking skeleton is functional: zero-prompt init, idempotent sync, four adapters, identity model, hooks installer, full test suite.

### What's in the package

```
dotagent/
├── pyproject.toml                # pipx-installable; entrypoint = dotagent.cli:main
├── README.md
├── .gitignore
├── docs/
│   └── SPEC.md                   # full design spec
├── src/dotagent/
│   ├── __init__.py __main__.py cli.py
│   ├── paths.py util.py config.py
│   ├── identity.py               # actor model: ~/.config/dotagent → git config → user
│   ├── discovery.py              # silent repo scan: lang/framework/lint/git log/CCO assets
│   ├── llm.py                    # Anthropic SDK wrapper (graceful fallback if no API key)
│   ├── hooks.py                  # git pre/post-commit + claude post-tool installer
│   ├── scaffold.py               # materializes the canonical .agent/ tree
│   ├── memory/
│   │   ├── working.py            # per-actor session JSON
│   │   ├── episodic.py           # append-only JSONL: <actor>__<session>.jsonl
│   │   ├── semantic.py           # content-hashed slugs, mandatory rationale fields
│   │   └── personal.py           # per-actor profile.yaml, never merged
│   ├── adapters/
│   │   ├── base.py
│   │   ├── claude.py             # CLAUDE.md
│   │   ├── cursor.py             # .cursorrules
│   │   ├── copilot.py            # .github/copilot-instructions.md
│   │   └── opencode.py           # AGENTS.md
│   ├── commands/
│   │   ├── init_cmd.py           # dotagent init
│   │   ├── sync_cmd.py           # dotagent sync
│   │   ├── identity_cmd.py       # dotagent identity show|set
│   │   ├── status_cmd.py         # dotagent status
│   │   └── observe_cmd.py        # dotagent observe (called by hooks)
│   └── scaffolds/agent/          # bundled .agent/ template content
│       ├── style.md rules.md architecture.md patterns.md preferences.md
│       ├── skills/               # observer, research, plan, code, review (5)
│       └── tools/                # git-proxy, pattern-extractor, memory-manager,
│                                 # debug-investigator, deploy-checklist (5)
└── tests/
    ├── test_smoke.py             # version, defaults, scaffold idempotency, discovery
    └── test_adapters.py          # 4 adapters render, episodic naming, semantic hashing
```

### Plug-and-play install (works today)

Install once per machine:

```bash
pipx install dotagent
```

Initialize in any repo (new or existing):

```bash
cd ~/code/your-repo
dotagent init       # zero prompts; ~30s; --interactive for the question flow
git add .agent/ CLAUDE.md .cursorrules .github/copilot-instructions.md AGENTS.md \
        .claude/hooks/post-tool.sh
git commit -m "chore: add dotagent context"
git push
```

Each teammate, once:

```bash
pipx install dotagent
git pull
dotagent sync       # rebuilds adapters locally + installs hooks; identity = git config user.email
```

### What `dotagent init` does (silently, no prompts by default)

1. **Discovery** — scans languages, frameworks, lint/test config, README, git log (last 500 commits), CI files, monorepo layout, existing CLAUDE.md / .cursorrules / .github/copilot-instructions.md / AGENTS.md, Claude-Code-Optimization assets.
2. **LLM draft** (if `ANTHROPIC_API_KEY` set) — drafts `.agent/{style,rules,architecture,patterns,preferences}.md` from discovery. Falls back to scaffold defaults otherwise.
3. **Identity** — resolves actor from `~/.config/dotagent/identity.yaml` → `git config user.email` → `getpass.getuser()`.
4. **Scaffold** — writes the canonical `.agent/` tree: 5 source mds + 5 skill mds + 5 tool mds + memory/working/episodic/semantic/personal/dream subdirectories.
5. **Render adapters** — CLAUDE.md, .cursorrules, .github/copilot-instructions.md, AGENTS.md (per `config.yaml`).
6. **Install hooks** — git pre-commit / post-commit (forward to `dotagent observe`), Claude Code `.claude/hooks/post-tool.sh`.

### Multi-developer + multi-AI-tool tracking — wired in

Every event records:

| Field | Resolved from |
| --- | --- |
| `actor` | `~/.config/dotagent/identity.yaml` → fallback `git config user.email` → fallback `getpass.getuser()` |
| `tool` | `--tool` flag on `dotagent observe` (set per-platform: `claude_code` / `cursor` / `copilot` / `opencode` / `cli`) |
| `host` | `socket.gethostname()` |
| `session` | UUID4-12 per invocation |

Filesystem invariants (built into Phase 1 code):

- Episodic JSONL: `memory/episodic/YYYY/MM/DD/<actor>__<session>.jsonl` → zero merge conflicts across teammates
- Semantic entries: SHA1-prefixed slug → collision-free across teammates
- Personal memory: `memory/personal/<actor-id>/` → never merged, never shipped to other actors' adapter outputs

### Verification

```bash
cd dotagent-pkg     # or wherever you unzipped
pip install -e .[dev]
pytest tests/ -v    # smoke + adapter tests pass

cd /tmp && rm -rf demo && mkdir demo && cd demo && git init && git commit --allow-empty -m init
dotagent init --no-llm
ls .agent CLAUDE.md .cursorrules .github AGENTS.md
dotagent status
dotagent identity show
dotagent sync       # idempotent
```

## What's left

### Phase 1 polish (not blocking, but nice)

- **Existing-CLAUDE.md ingest**: on `dotagent init`, if CLAUDE.md / .cursorrules / .github/copilot-instructions.md / AGENTS.md exist, parse them and seed `.agent/{style,rules,architecture,patterns,preferences}.md` before overwriting. Today it overwrites with scaffold/LLM content, losing existing hand-written copy.
- **`--dry-run`** flag is wired but should also show a unified diff vs existing files before any write.
- **Refactor source loading** so `.agent/config.yaml`'s `sources:` block can reference existing `<project>/docs/` files (e.g. `docs/bug-registry.md`, `docs/anti-patterns.md`), making `docs/` the source of truth and `.agent/` an index — not a duplicate. Critical for projects with established `docs/` conventions.

### Phase 2 — Episodic + visibility

- Episodic SQLite index (`memory/episodic/index.sqlite` with FTS + vector embeddings).
- `dotagent who --file <path>` — every actor that touched the file, with tool used.
- `dotagent who --rule <slug>` — proposer + graduator + evidence actors.
- `dotagent activity --since 7d --by <id> --tool <name>` — filtered event feed.
- `dotagent leaderboard --since 30d` — graduations / file touches / signals per dev.
- `dotagent feed` — chronological team-wide event stream.
- `dotagent timeline <file>` — per-file edit history.
- Git Proxy adds `Co-authored-by: dotagent <tool=claude_code,actor=alice>` commit trailer (so attribution survives in `git log` even without dotagent installed).
- Cursor hook shim (file-watcher fallback if Cursor < 0.40).
- Copilot heuristic attribution (timing + commit trailer; opt-in VS Code extension to be explicit).

### Phase 3 — Skills runtime

- `dotagent skill run observer|research|plan|code|review`
- Skill loader (markdown + frontmatter parsing)
- Skill composition: Observer → Research → Plan → Code → Review pipeline

### Phase 4 — Tools runtime

- **Pattern Extractor** — static analysis (madge / ts-morph / Python ast / go list) emits semantic patterns into `memory/semantic/patterns/`
- **Memory Manager** — full CRUD + search + summarize across all four stores
- **Debug Investigator** — given a stack trace, walks episodic memory across all teammates for similar past failures; cites prior event ids
- **Deploy Checklist** — generates a deploy gate from `rules.md` + recent risk signals (reverts, failed CI)

### Phase 5 — Auto-Dream pipeline

- Signal extraction (revert ≥ 2, same error sig ≥ 3, cross-actor anti-pattern, ...)
- Embed + cluster (HDBSCAN, cosine)
- LLM judge → cluster summary
- **Graduation gate with mandatory rationale** — every graduated rule writes `dream/graduated/<id>.md` with rationale + evidence + graduated_by; rejected ones land in `dream/rejected/` with rationale
- CRON installer (daily / weekly / monthly schedules)
- GitHub Action template — runs Auto-Dream nightly, opens a PR with rationale-bearing files for human review/merge
- Resync trigger after every graduation

### Phase 6 — Polish

- Custom adapter via Jinja templates (user-defined output paths)
- Multi-repo / workspace mode
- `--import-claude-code-optimization` migrator — ingest existing `docs/bug-registry.md`, `docs/anti-patterns.md`, `docs/redis-key-registry.md`, `docs/db-impact-map.md`, `docs/dependency-map.md`, `prompts/*` into the new structure (lossless, references not copies, per the docs-as-source-of-truth refactor)
- Optional `dotagent server` for centralized teams (real-time event stream, RBAC, dashboards)

## State of the source code

The Phase 1 code currently exists in two places:

1. In the `dotagent.zip` artifact (and unzipped at `/home/user/dotagent-pkg/` in the build sandbox) — the canonical reference once moved to a real repo.
2. As four orphan commits on `dilawarabbas1/aigent-backend`:
   - `7c4dd89` — package skeleton + core
   - `f91e74c` — memory + adapters + commands
   - `933c69b` — scaffolds (`.agent/` templates)
   - `318e1a4` — tests + DOTAGENT_FRAMEWORK spec doc
3. The branch `claude/ai-coding-tools-config-WbtVP` was force-reset to point at main's HEAD, so the dotagent code is not visible in any branch tree. Commits remain reachable by SHA until the branch is deleted and GitHub GC runs. **Action item for user:** delete the branch via https://github.com/dilawarabbas1/aigent-backend/branches → trash icon. Then GitHub GC (~2 weeks) will purge the orphan commits.

The intended permanent home is `github.com/dilawarabbas1/dotagent` (empty repo already created by user, but not in this Claude session's scope — needs new session or scope widening to push there).

## How to resume in a new Claude session

Paste this as the first message:

```
Continuing dotagent work. Read /path/to/PROJECT_CONTEXT.md (this file) for full state.

Current priorities:
1. Phase 1 polish — existing-CLAUDE.md ingest on init; docs/-as-source-of-truth refactor; --dry-run unified diff.
2. Phase 2 — episodic SQLite index + dotagent who/activity/feed/timeline/leaderboard + commit trailer.

Important: aigent-backend should NOT have any dotagent code committed; if you see it there, the user wants it removed.
```

## Architecture decisions (locked)

1. `.agent/` is a generalized superset of Claude-Code-Optimization's `.claude/` + `docs/` + `prompts/`. Every legacy asset has a documented new home; nothing is dropped.
2. `docs/` is the source of truth for a project's knowledge, not `.agent/`. dotagent indexes `docs/` via `config.yaml` `sources:` (Phase 1 polish item — currently the source files live inside `.agent/*.md` only).
3. **Plug-and-play default**: `dotagent init` is zero-prompt. `--interactive` opt-in for the 8–15 question wizard. All decisions have sensible defaults.
4. **Identity is the human, tool is the AI platform.** They're separate fields on every event. Same human → multiple AI tools = one actor with multiple events tagged differently.
5. **Memory committed to git is shared; personal memory is per-actor and never merged.** Episodic JSONL filenames + semantic content-hashed slugs guarantee zero conflicts on merge.
6. **Auto-Dream graduations require a written rationale** — non-negotiable. The rationale file IS the audit of agent learning.
7. Adapter outputs cite `docs/` sources in their generated headers, so a reader of a generated CLAUDE.md can trace back to the canonical doc.

## Naming

`dotagent` (chosen). Rejected alternatives: `mneme`, `praxis`, `rosetta`, `aigent` (collides with user's aigent-portal/backend/admin product).
