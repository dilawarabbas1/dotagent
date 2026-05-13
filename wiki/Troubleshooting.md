# Troubleshooting

## First line of defense

```bash
dotagent doctor
```

Checks Python version, git presence, `ANTHROPIC_API_KEY`, `.agent/` state,
configured sources, hooks installed, episodic index health, cache gitignore,
optional-extras availability. Exits nonzero on any `fail`. Output is
designed to be paste-able into an issue.

For more detail:

```bash
DOTAGENT_DEBUG=1 dotagent <whatever>     # surface silenced exceptions on stderr
```

## Common issues

### CLAUDE.md doesn't update after editing `docs/bug-registry.md`

The auto-reindex only fires when `dotagent observe` sees a `docs/*.md`
change (i.e. when you commit or when Claude Code's post-tool hook fires).
Manual edits without committing won't trigger it.

Fix:

```bash
dotagent sync         # re-indexes + re-renders
# or just the reindex:
dotagent reindex
```

### `dotagent who --file <path>` returns nothing

The SQLite event index may be missing or stale.

```bash
dotagent reindex-events     # rebuild from JSONL
dotagent who --file <path>
```

### `dotagent skill run` says "ANTHROPIC_API_KEY not set"

That's expected when the key isn't in the environment. Either:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
dotagent skill run plan --task "..."
```

Or run dry to inspect the prompt without making an API call:

```bash
dotagent skill run plan --task "..." --dry-run
# prints the resolved system + user prompts
```

### Commit trailer not appearing in `git log`

Verify the hook exists and is executable:

```bash
ls -la .git/hooks/prepare-commit-msg
# should be -rwxr-xr-x ... and contain `dotagent`

# if missing:
dotagent sync     # reinstalls hooks
```

Note: trailers are added to **new commits** via `prepare-commit-msg`. They
don't get backfilled into existing commits.

### Cursor watcher emits events even when I wasn't using Cursor

The watcher uses `pgrep -f cursor` as a heuristic: if any Cursor process
is running, file edits in the watched repo are tagged `tool=cursor`.
This catches the common case but isn't perfect — if you're typing in vim
while Cursor is also open in the background, your edits get tagged
`tool=cursor`.

Fix: close Cursor when you're not using it, or rely on Cursor 0.40+'s
native hooks (drop the watcher entirely).

### "migrate-cco reported nothing"

Your repo doesn't match the Claude-Code-Optimization layout exactly. To
wire it manually, edit `.agent/config.yaml`:

```yaml
sources:
  bug_registry: docs/whatever-you-call-it.md
  anti_patterns: docs/your-anti-patterns.md
  # ...
```

Then `dotagent reindex && dotagent sync`.

### `pipx install` 401/403 from GitHub

Your local git auth isn't configured or doesn't have access to the repo.
If it's a private repo, generate a personal access token and:

```bash
pipx install "git+https://<token>@github.com/dilawarabbas1/dotagent"
```

### Generated CLAUDE.md is too long for Claude Code's context

Reduce the embedded entries via `.agent/config.yaml`:

```yaml
context:
  bug_registry_top_n: 8     # was 15
  anti_patterns_top_n: 5    # was 10
  recent_activity_top_n: 4  # was 8
```

`dotagent sync` regenerates with fewer entries. The full docs/ remain
linked in the source-pointer footer, so the AI agent can fetch detail
on demand.

### `dotagent serve` 500s on POST /events

Set `DOTAGENT_DEBUG=1` on the server host and rerun — it'll print the
traceback. Most likely cause: malformed JSON in the request body, or a
token without `writer`+ role.

### Embedding clustering crashes / takes forever

The first run downloads `all-MiniLM-L6-v2` (~22MB) which can be slow on
flaky connections. Subsequent runs use the cached model.

If you don't want embeddings: `dotagent dream run --no-embeddings` (the
heuristic clusters still run).

### "Personal preferences for `alice` shows my teammate's prefs"

Your active actor is wrong. Run:

```bash
dotagent identity show
```

Fix:

```bash
dotagent identity set --id <your-id> --name "..." --email "..."
dotagent sync
```

The personal section reads from
`.agent/memory/personal/<resolved-actor>/profile.yaml` — if the resolved
actor was wrong, you got someone else's prefs.

### Tests pass locally but fail in CI

Two common causes:

1. **Optional extras missing.** CI installs `[dev,server]` by default. If
   a test imports from `[ml]` or `[watch]`, gate it with
   `pytest.importorskip` or `@pytest.mark.skipif`.
2. **Working directory.** `find_repo_root()` walks up looking for `.git/`
   or `.agent/`. Tests must use `tmp_path` and not assume CWD.

## When `dotagent doctor` says "warn"

Each `warn` includes a `fix:` line telling you exactly what to run. The
common ones:

| Warning | Fix |
|---------|-----|
| `sources: No sources configured` | Edit `.agent/config.yaml` to point at your docs |
| `sources: 0/N configured sources exist on disk` | Create at least one docs/*.md or change the config paths |
| `hooks: git hooks missing dotagent wiring` | `dotagent sync` |
| `hooks: Claude Code post-tool hook is missing` | `dotagent sync` |
| `episodic_index: JSONL files exist but no SQLite index` | `dotagent reindex-events` |
| `cache_gitignore: missing` | `dotagent reindex` (regenerates the .gitignore) |

## Filing a good bug report

```bash
dotagent --version
python --version
dotagent doctor --format json
```

…paste those in an issue along with the minimum command sequence that
reproduces the problem. If it's a docs-parsing issue, also attach the
docs/*.md file in question (sanitize if needed).
