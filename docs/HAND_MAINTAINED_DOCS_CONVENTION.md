# Hand-maintained docs convention

## Hard boundary

> dotagent's role for the paths below is **READ + REFERENCE only**.
>
> dotagent WILL NOT generate, author, render-the-content-of, or overwrite any of these files. They are owned by the project team + Claude. dotagent only indexes them as sources and surfaces pointers in rendered adapters.

If you see dotagent writing to any of these paths, **that's a bug** — file an issue. The boundary is enforced by `test_regenerate_derived_files_never_writes_hand_maintained` which snapshots sentinel content and asserts it's unchanged after a full orchestrator run.

---

## The structure

```
docs/
├── feature_master.md                              Entry-point index (FM-###)
├── feature_master/FM-###-<slug>.md                Per-feature record
├── db-impact-map-{master,tenant,vector}.md        Deep DB dependency
├── redis-key-registry-{tenant,global,events}.md   Deep Redis dependency
├── anti-patterns.md                               AP-### rules
├── bug-registry-{infrastructure,agents,           DA-BUG history (sharded)
│                orchestrator}.md
├── ARCHITECTURE.md                                System design narrative
└── ops/
    ├── service-registry.md                        Processes (pm2/port/host)
    ├── server-dependencies.md                     Native packages + versions
    ├── tuning.md                                  DB/Redis/pm2/nginx tuning
    └── tls-and-env.md                             TLS + env-var reference
```

### Entry point

`docs/feature_master.md` is THE entry point. An agent working on a feature follows: `feature_master.md` → matching `FM-###-<slug>.md` → its file-path / service-name references into deep registries. The rendered CLAUDE.md surfaces this navigation in the "📑 Feature documentation (hand-maintained)" section near the top.

### Per-feature record shape

Each `FM-###-<slug>.md` is expected to carry:
- **contract** — what the feature does
- **design** — why it's built that way
- **invariants** — what must never become false (AP-### refs)
- **files** — host · route · db→ · redis→ · external

The fields are the discovery surface; dotagent doesn't enforce shape. Authors can evolve. Just keep `feature_master.md` as the index and use `## files` (or `## Files:`, `### files`) so `dotagent doc-coverage` can parse the file list.

### Join keys

| From | Join on | To |
|---|---|---|
| `feature_master.md` row | `FM-###` | `feature_master/FM-###-<slug>.md` |
| `FM-###-<slug>.md` files: section | file path | `db-impact-map-*.md` · `redis-key-registry-*.md` · `anti-patterns.md` · `bug-registry-*.md` |
| `FM-###-<slug>.md` host: section | service name | `ops/service-registry.md` |
| `FM-###` | `FEAT-NN` | `.agent/project/modules/<id>/cycles/<NN>/contract.frozen.md` |

---

## dotagent's role

**WILL:**
- Surface every path as a navigation pointer in rendered adapters (`HAND-MAINTAINED ·` prefix in description).
- Index each file as a source (`DEFAULT_CONFIG.sources.extra` in `config.py`).
- Treat them as KNOWN schema entries (structure-checker won't flag them).
- Read them for `dotagent doc-coverage` (the FM-### parser + required-doc checklist).

**WILL NOT:**
- Generate any of these files. Ever.
- Add them to `regenerate_derived_files()` or any write path.
- Overwrite on `dotagent sync` or `dotagent project regenerate`.
- Stage them on commit hooks.
- Treat their absence as an error — every schema entry is `required=False`.

---

## Coexistence with other conventions

| Path | Owner |
|---|---|
| `docs/bug-registry.md` | Hand-maintained — single-file convention |
| `docs/bug-registry-{infrastructure,agents,orchestrator}.md` | Hand-maintained — sharded layered convention |
| `docs/redis-keys.md` | Hand-maintained — single-file Redis catalog |
| `docs/redis-key-registry-{tenant,global,events}.md` | Hand-maintained — sharded deep variant |
| `docs/db-impact-map.md` | Hand-maintained — single-file impact map |
| `docs/db-impact-map-{master,tenant,vector}.md` | Hand-maintained — sharded deep variant |
| `docs/architecture.md` | Hand-maintained — long-form architecture (lowercase) |
| `docs/ARCHITECTURE.md` | Hand-maintained — design narrative (uppercase) — *why* |
| `docs/service-registry.md` | **GENERATED** by dotagent from `git.yaml` |
| `docs/ops/service-registry.md` | Hand-maintained — pm2/port/host process registry |

Single-file and sharded conventions both work; sharded is additive. The only collision to know about: `docs/service-registry.md` (generated git-repo table) vs `docs/ops/service-registry.md` (hand-maintained process registry). Different paths, different concepts.

---

## If you change this convention

Update all of these in the same PR:

1. `src/dotagent/canonical_structure.py` — schema entries
2. `src/dotagent/config.py` — `DEFAULT_CONFIG.sources.extra`
3. `src/dotagent/render/manifest.py` — `_CATEGORY_PREFACE` text
4. `tests/render/test_hand_maintained_docs.py` — regression tests
5. This document

---

## Verbatim source spec

_The text below is the canonical request that introduced this convention. Preserve verbatim if you edit this document._

> SUBJECT: Register a hand-maintained documentation structure as referenceable sources — DO NOT generate or own these files.
>
> CONTEXT: My project has a documentation system that I (the human) + Claude maintain by hand. I need dotagent to UNDERSTAND this structure and be able to REFERENCE it in the adapters/files dotagent renders (CLAUDE.md, AGENTS.md, source pointers, etc.) — so an agent reading the adapter knows these docs exist, what each holds, and how to navigate them.
>
> HARD BOUNDARY — dotagent's role here is READ + REFERENCE only:
>   - DO NOT generate, author, render-the-content-of, or overwrite any of these files.
>   - DO NOT treat them as generated surfaces (they are NOT like SCOPE.md / CONTRACTS.md).
>   - DO index them as SOURCES and surface pointers to them in the rendered adapters, exactly as you already do for db-impact-map / redis-key-registry / anti-patterns.
>   - The content is owned by humans + Claude. You only point at it.
>
> ENTRY POINT: feature_master.md is the index. An agent working on a feature should be pointed to feature_master.md → the matching FM-###-<slug>.md → then follow its file-path / service-name references into the deep registries.

---

## Related

- `CLAUDE_MD_DESIGN.md` — ownership rule + manifest design
- `DERIVED_FILES_DESIGN.md` — what dotagent DOES generate (contrast)
- `DOC_COVERAGE_CLI.md` — `dotagent doc-coverage` reads this convention
- `tests/render/test_hand_maintained_docs.py` — regression tests (67)
