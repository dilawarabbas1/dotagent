# dotagent — examples

Sample `docs/*.md` files showing the format the built-in parsers expect.
None of this is mandatory — the parsers are tolerant — but matching this
shape gives you the cleanest extraction.

## Trying it locally

```bash
cd examples
git init && git add . && git commit -m "examples"
dotagent init --no-llm
dotagent sync
cat CLAUDE.md     # see the rendered context with bugs, anti-patterns, etc.
```

## Files

- [`docs/bug-registry.md`](docs/bug-registry.md) — `## ID: title` + bulleted
  metadata (severity, files, component)
- [`docs/anti-patterns.md`](docs/anti-patterns.md) — same shape as bug-registry
- [`docs/redis-key-registry.md`](docs/redis-key-registry.md) — keys extracted
  from backticks and `keys:` metadata
- [`docs/db-impact-map.md`](docs/db-impact-map.md) — tables extracted from
  `tables:` metadata and `table.column` references in the body
- [`docs/dependency-map.md`](docs/dependency-map.md) — services extracted from
  `services:` metadata and `A → B` arrows in bullets
- [`docs/architecture.md`](docs/architecture.md) — each H2 is a section
