# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-06

First launch-ready release. Brings the walking-skeleton from 0.1.0 to a usable
end-to-end system: every memory, every adapter, every visibility command,
auto-dream graduation with mandatory rationale, the four built-in tools, the
skills runtime, the centralized server, and the Cursor + Copilot bridges.

### Added — context & memory
- `docs/` is wired as the canonical source of truth via `.agent/config.yaml`
  `sources:` block. Six built-in source kinds (bug-registry, anti-patterns,
  redis-keys, db-impact-map, dependency-map, architecture) with tolerant
  markdown parsers; arbitrary extras via `sources.extra`.
- Pointer cards committed at `.agent/memory/semantic/sources/<id>.md`;
  structured cache (gitignored) at `.agent/.cache/sources.json`.
- Unified `dotagent.context.build()` resolver merges five `.agent/*.md` files +
  indexed sources + semantic memory + personal memory + working memory + recent
  episodic events into one `Context` object.
- Per-actor working-memory `current.json` tracks branch / recent files /
  recent events / current task. Updated by every observed event.
- `dotagent.ingest` parses existing `CLAUDE.md` / `.cursorrules` /
  `.github/copilot-instructions.md` / `AGENTS.md` and routes H2 sections into
  the matching `.agent/*.md` bucket on init (hand-written copy survives).

### Added — adapters
- All four adapters (Claude Code, Cursor, Copilot, OpenCode) render the full
  `Context`: project rules, ranked bug registry, anti-patterns, DB hotspots,
  redis keys, dependency map, architecture pointers, personal preferences for
  the active actor, working-memory snapshot, recent activity, and a source-of-
  truth footer.
- `CustomAdapter` renders Jinja templates from
  `.agent/adapters/custom/templates/*.j2` with `{# output: <path> #}`
  directives.

### Added — visibility (Phase 2)
- SQLite event index auto-built from episodic JSONL.
- Commands: `who --file/--rule`, `activity`, `timeline`, `feed`,
  `leaderboard`, `reindex-events`.
- `prepare-commit-msg` hook + `dotagent trailer` add a `Co-authored-by:
  dotagent ... actor=X tool=Y` trailer so attribution survives in `git log`.

### Added — skills (Phase 3)
- Skill loader parses YAML frontmatter + body from `.agent/skills/*.md`.
- Commands: `skill list/show/run/pipeline`. LLM-backed via `anthropic`;
  without API key returns the resolved prompt for inspection.

### Added — tools (Phase 4)
- `tool pattern-extractor` — Python AST + JS/TS regex import scan, emits
  `SemanticEntry` records.
- `tool memory <query>` — search across all four memory stores; `--summary`
  for store-level counts.
- `tool debug <stack>` — match a stack trace against episodic memory +
  bug registry.
- `tool checklist --since` — synthesize a pre-deploy gate from rules.md +
  bug-registry + recent reverts/fixes.

### Added — auto-dream (Phase 5)
- Heuristic signal extraction (revert clusters, repeat-fix, frequent-failure,
  cross-actor anti-pattern).
- Embedding-based clusters via sentence-transformers + sklearn DBSCAN (opt-in
  via `pip install 'dotagent[ml]'`).
- `dream run / list / graduate / reject` — graduate/reject require a
  non-empty rationale (raises `ValueError` otherwise). Graduations flow into
  semantic memory as `auto-dream` rules.
- `dream cron-install / cron-uninstall`, `dream github-action` writes a
  workflow template.

### Added — polish (Phase 6)
- `sync --dry-run` shows unified diff vs on-disk files.
- `migrate-cco` — lossless Claude-Code-Optimization migrator: references
  docs/ as sources (no copy), imports `prompts/*.md` as
  `.agent/skills/imported-<slug>.md`, ingests existing CLAUDE.md.

### Added — Phase 7 closeout
- **Cursor < 0.40 file-watcher fallback.** `dotagent watch cursor` debounces
  file events (2s window), gates on a running Cursor process, forwards as
  `tool=cursor`. Requires `pip install 'dotagent[watch]'`.
- **dotagent server.** FastAPI app with token RBAC (admin/writer/reader),
  `POST /events`, `GET /events`, SSE stream, token management, live
  dashboard. SQLite persistence. `dotagent serve --host/--port`. Requires
  `pip install 'dotagent[server]'`. Clients forward via
  `.agent/config.yaml` `server.url/token/forward_events`.
- **VS Code Copilot extension scaffold** at `extensions/vscode-copilot/`.
  Listens for inline-suggest commands; saves/edits inside a timing window
  forward to `dotagent observe ... --tool copilot`.

### Added — operations
- `dotagent doctor` — self-check for common misconfigurations.
- `DOTAGENT_DEBUG=1` enables debug logging (silent `except` paths now log).
- GitHub Actions CI: `tests` on push/PR across Python 3.11 + 3.12.
- `examples/` folder with a sample project showing the expected `docs/*.md`
  format.

### pyproject extras
- `[ml]` — sentence-transformers + scikit-learn for embedding clusters.
- `[server]` — fastapi + uvicorn + starlette.
- `[watch]` — watchdog (Cursor file-watcher).
- `[all]` — all three above.
- `[dev]` — pytest + ruff for contributors.

### Tests
- 60 → 65+ passing (Phase 7 closeout + doctor coverage).

## [0.1.0] — 2026-05-05

Initial walking-skeleton release. Zero-prompt `dotagent init`, idempotent
`sync`, four adapters (claude / cursor / copilot / opencode), identity model,
git + Claude Code hooks, four-memory scaffolding, full test suite (13 tests).
The package is plug-and-play but `docs/` is not yet wired as the source of
truth — that came in 0.2.0.
