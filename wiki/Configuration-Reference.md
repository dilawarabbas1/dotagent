# Configuration Reference

Every key in `.agent/config.yaml`, with defaults and what they do.

## Full default config

```yaml
project:
  name: ""                  # auto-set to repo dir name on init
  description: ""

adapters:
  claude: true              # generate CLAUDE.md
  cursor: true              # generate .cursorrules
  copilot: true             # generate .github/copilot-instructions.md
  opencode: false           # generate AGENTS.md
  custom: false             # render Jinja templates from .agent/adapters/custom/templates/*.j2

sources:
  bug_registry: docs/bug-registry.md
  anti_patterns: docs/anti-patterns.md
  redis_keys: docs/redis-key-registry.md
  db_impact_map: docs/db-impact-map.md
  dependency_map: docs/dependency-map.md
  architecture: docs/architecture.md
  extra: []                 # see below

context:
  bug_registry_top_n: 15    # top-N bugs (by severity) included in CLAUDE.md
  anti_patterns_top_n: 10
  recent_activity_top_n: 8  # recent episodic events shown
  embed_full_docs: false    # also cache the full doc text in sources.json

server:
  url: ""                   # e.g. https://dotagent.internal:9700
  token: ""                 # writer or admin token
  forward_events: false     # POST every observed event to the server

dream:
  enabled: true
  cron:
    daily:   "0 2 * * *"
    weekly:  "0 9 * * 1"
    monthly: "0 9 1 * *"
  min_cluster_size: 3
  window_days: 14

share:
  episodic: full            # full / summary / none
  semantic: full            # full / summary / none
  personal: never           # per-actor; never shared

pii:
  redact_secrets: true
  redact_paths:
    - "**/.env*"
    - "**/secrets/**"

hooks:
  git_pre_commit: true
  git_post_commit: true
  block_on_rule_violation: false
```

## Section-by-section

### `project`
Cosmetic. `project.name` appears in the rendered CLAUDE.md header.

### `adapters`
Set `false` to skip generation. Adapters write to fixed paths:

| Key | Output |
|-----|--------|
| `claude` | `CLAUDE.md` |
| `cursor` | `.cursorrules` |
| `copilot` | `.github/copilot-instructions.md` |
| `opencode` | `AGENTS.md` |
| `custom` | rendered from `.agent/adapters/custom/templates/*.j2` |

### `sources`
Logical name → repo-relative path. Built-in names (bug_registry, anti_patterns,
redis_keys, db_impact_map, dependency_map, architecture) use their dedicated
parsers. Anything else uses the generic parser.

`sources.extra` adds arbitrary docs:

```yaml
sources:
  extra:
    - name: api_contracts
      path: docs/api/contracts.md
      kind: generic
    - name: oncall
      path: docs/runbooks/oncall.md
      kind: generic
```

### `context`
Controls how many entries appear in CLAUDE.md. The rest stays in `docs/` —
the AI agent reads the source-pointer footer to fetch the full file.

- `embed_full_docs: true` — also cache the entire doc text in
  `.agent/.cache/sources.json`. Skills like `tool memory <query>` can then
  search the full text. Costs disk space; usually unnecessary.

### `server`
Optional centralized server. Set `forward_events: true` and `url`/`token`
to make `dotagent observe` POST every event to the server in addition to
writing locally. See [[Server and RBAC]].

### `dream`
Auto-Dream tuning.

- `min_cluster_size` — minimum events needed to form a heuristic signal.
- `cron` — schedule strings (cron format) used when generating the GitHub
  Action template or installing local cron entries.

### `share`
What memory is committed to git vs kept local. Defaults are sensible:
episodic + semantic shared, personal never.

### `pii`
Redaction rules (currently applied to scaffold defaults; full enforcement
is on the polish list).

### `hooks`
Whether to install each hook on `init` / `sync`. `block_on_rule_violation`
is reserved for a future "fail commit if it violates a graduated rule"
feature.

## Per-project vs per-machine

The `.agent/config.yaml` is per-project. `~/.config/dotagent/identity.yaml`
is per-machine (one identity, every project). The two never mix.

## Editing config safely

```bash
# show current config
cat .agent/config.yaml

# edit (any text editor)
vim .agent/config.yaml

# verify it loads cleanly
dotagent status

# regenerate adapters from the new config
dotagent sync
```

`dotagent doctor` will flag obvious mistakes (missing sources, etc.).

## Adding the custom adapter

To emit your own file format (say, a Markdown file at `docs/AI_CONTEXT.md`
for your own tooling to consume):

```bash
mkdir -p .agent/adapters/custom/templates
cat > .agent/adapters/custom/templates/ai_context.md.j2 <<'EOF'
{# output: docs/AI_CONTEXT.md #}
# {{ ctx.project_name }} — AI context

{{ render_body("custom integration") }}
EOF
```

Then in `.agent/config.yaml`:

```yaml
adapters:
  custom: true
```

Run `dotagent sync`. The Jinja template runs with `ctx` (the full Context)
plus `render_body(label)` helper that returns the same body the built-in
adapters use.
