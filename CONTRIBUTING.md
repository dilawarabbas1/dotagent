# Contributing to dotagent

Thanks for considering a contribution. dotagent is meant to be small,
opinionated, and battle-tested. PRs are welcome — read this first.

## Ground rules

- **Tests are required.** Every new feature, fix, and refactor lands with
  tests in the same PR. The bar is `pytest tests/ -q` clean.
- **Don't add features the goals don't require.** dotagent is intentionally
  small. The `.agent/rules.md` scaffold spells out the principle:
  > "Don't add a feature, abstraction, or fallback the task doesn't require."
- **`docs/` is sacred.** dotagent reads `docs/*.md` but never writes there.
  This is a hard invariant — no "helpful" generation into a user's `docs/`.
- **No silent failures.** Use the debug logging path (see `dotagent.logging`),
  not bare `except Exception: pass`.
- **Personal memory never leaks.** A teammate's personal preferences must
  never appear in another teammate's generated adapter outputs.

## Local development

```bash
git clone https://github.com/dilawarabbas1/dotagent
cd dotagent
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,all]'
pytest tests/ -v
```

## Adding a new source kind

`docs/your-thing.md` should be indexable. Wire it in three places:

1. **Parser** in `src/dotagent/sources.py` — add a `_parse_your_kind` function
   and register it in `_PARSERS`. Be tolerant of formatting variations.
2. **Default path** in `src/dotagent/config.py` `DEFAULT_CONFIG["sources"]`.
3. **Adapter section** in `src/dotagent/adapters/render.py` — add a
   `_render_your_kind` and call it from `render_body`.

Tests: add a `test_your_kind_parses_entries` in `tests/test_sources.py`.

## Adding a new adapter

Subclass `Adapter` in `src/dotagent/adapters/<your_tool>.py`. Use
`coerce_to_context` + `render_body` for consistency with the others.
Register it in `src/dotagent/adapters/__init__.py` `REGISTRY` and add to
`DEFAULT_CONFIG["adapters"]`. Tests in `tests/test_adapters.py`.

## Adding a new tool

Drop a module under `src/dotagent/tools/`, expose its entry from
`tools/__init__.py`, and add a Click command in
`src/dotagent/commands/tool_cmd.py`. Tests in `tests/test_phase4_tools.py`.

## Adding a new skill

Skills are markdown — drop one in `src/dotagent/scaffolds/agent/skills/`
with YAML frontmatter (`name`, `description`, optional `inputs`). It will
ship with every new project initialized via `dotagent init`.

## Reporting bugs

Open a GitHub issue. Include:

- `dotagent --version`
- `python --version`
- The output of `dotagent doctor`
- A minimal reproduction (a tarball of `.agent/` + the relevant `docs/*.md`
  if it's a parsing issue).

## Code style

- Python 3.11+; `ruff` for linting (`ruff check src tests`).
- No comments that restate what the code already says.
- Type-annotate public APIs.
- Keep error messages actionable: tell the user what to do, not just what
  went wrong.

## License

By contributing you agree your code is licensed under MIT.
