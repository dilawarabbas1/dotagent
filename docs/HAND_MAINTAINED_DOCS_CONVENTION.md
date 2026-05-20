# Hand-maintained docs convention

_Status: locked as of v0.4.11 · last updated 2026-05-20_

## Hard boundary

dotagent's role for the paths listed below is **READ + REFERENCE only**.

> dotagent will NOT generate, author, render-the-content-of, or overwrite
> any of these files. They are owned by the project team + Claude.
> dotagent only indexes them as sources and surfaces pointers in the
> rendered adapters (CLAUDE.md / AGENTS.md / .cursorrules / copilot).

This is the same model dotagent already uses for `docs/bug-registry.md`,
`docs/anti-patterns.md`, `docs/redis-keys.md`, etc. The 0.4.11 release
extends the model to a richer hand-maintained documentation structure:
**features**, **operations**, and **deep dependency registries**.

If you change this convention, update this document AND the schema
entries in `src/dotagent/canonical_structure.py` AND the source defaults
in `src/dotagent/config.py` AND the test in
`tests/render/test_hand_maintained_docs.py` in the same PR.

---

## The structure

```
docs/
├── feature_master.md                              Index of all features
├── feature_master/FM-###-<slug>.md                Per-feature record
├── db-impact-map-{master,tenant,vector}.md        DB dependency (deep)
├── redis-key-registry-{tenant,global,events}.md   Redis dependency (deep)
├── anti-patterns.md                               AP-### rules → feature invariants
├── bug-registry-{infrastructure,agents,           DA-BUG history (sharded)
│                orchestrator}.md
├── ARCHITECTURE.md                                System design narrative ("why")
└── ops/
    ├── service-registry.md                        Processes that must run
    ├── server-dependencies.md                     Native packages + versions
    ├── tuning.md                                  DB/Redis/pm2/nginx tuning
    └── tls-and-env.md                             TLS certs + env-var reference
```

### Entry point

**`docs/feature_master.md`** is THE entry point. An agent working on a
feature should be pointed to `feature_master.md` first, then the matching
`FM-###-<slug>.md`, then follow its file-path / service-name references
into the deep registries.

The rendered CLAUDE.md surfaces this navigation explicitly in the
"📑 Feature documentation (hand-maintained)" section header.

### Per-feature file shape

Each `FM-###-<slug>.md` is expected to carry:

- **contract** — *what* the feature does (the agreement)
- **design** — *why* it's built that way (rationale)
- **invariants** — what must never become false (AP-### refs)
- **files** — host · route · db→ · redis→ · external deps

The fields above are the discovery surface; dotagent doesn't enforce or
parse them. Authors are free to evolve the shape — just keep
`feature_master.md` as the index.

### Naming conventions

- `FM-` prefix → feature-master record (numeric ID, slug suffix).
- `DA-BUG-INFRA-`, `DA-BUG-AGT-`, `DA-BUG-ORCH-` → layered bug IDs.
- `AP-` → anti-pattern entry.

### Join keys (for cross-reference navigation)

| From | Join on | To |
|---|---|---|
| `feature_master.md` row | `FM-###` | `feature_master/FM-###-<slug>.md` |
| `FM-###-<slug>.md` files: section | file path | `db-impact-map-*.md`, `redis-key-registry-*.md`, `anti-patterns.md`, `bug-registry-*.md` |
| `FM-###-<slug>.md` host: section | service name | `ops/service-registry.md` |
| `FM-###` | `FEAT-NN` | `.agent/project/modules/<id>/cycles/<NN>/contract.frozen.md` |

---

## dotagent's role

**dotagent WILL:**
- Surface every path above as a navigation pointer in the rendered adapter (CLAUDE.md and sister files). Pointers carry the `HAND-MAINTAINED ·` prefix in their `when_to_read` text.
- Index each file as a source so it shows up in `dotagent context` output and the pointer cards under `.agent/cache/`.
- Treat them as KNOWN schema entries — the structure-checker won't flag them as deviations.

**dotagent will NOT:**
- Generate any of these files. Ever.
- Add them to `regenerate_derived_files()` or any write path.
- Overwrite them on `dotagent sync` or `dotagent project regenerate`.
- Stage them on commit hooks.
- Treat their absence as an error — every entry is `required=False`.

If you see dotagent writing to any of these paths, **that's a bug**.
File an issue.

---

## Implementation

### Schema entries

`src/dotagent/canonical_structure.py` declares each path with:
- `kind=KIND_FILE` (NOT `KIND_GENERATED`)
- `required=False` (optional — projects opt in by creating the files)
- Appropriate category: `CAT_FEATURE_DOCS`, `CAT_DATA_LAYER`, `CAT_BUGS`,
  `CAT_ARCHITECTURE`, `CAT_OPS`
- `when_to_read` prefixed with `HAND-MAINTAINED ·`

### Source defaults

`src/dotagent/config.py`'s `DEFAULT_CONFIG.sources.extra` registers each
file with its appropriate `kind` (so `bug-registry-*.md` files get
parsed by the bug-registry indexer, etc.).

### Adapter pointer

The manifest renderer (`src/dotagent/render/manifest.py`) places
`CAT_FEATURE_DOCS` near the top of the navigation index (right after
Business intent) and prepends a `_CATEGORY_PREFACE` paragraph:

> **Entry point for any feature work:** read `docs/feature_master.md`
> first (the FM-### index), then open the matching
> `docs/feature_master/FM-###-<slug>.md` for that feature's contract,
> design rationale, invariants, and files (host · route · db→ · redis→ ·
> external). From there, follow file-path references into the deep
> registries below.

`CAT_OPS` sits near `CAT_CONFIG` with its own preface explaining it's
hand-maintained.

---

## Coexistence with dotagent's other conventions

| Path | Owner | What it is |
|---|---|---|
| `docs/bug-registry.md` | Hand-maintained | Flat single-file bug log (default convention) |
| `docs/bug-registry-{infrastructure,agents,orchestrator}.md` | Hand-maintained | Sharded layered variant (this convention) |
| `docs/redis-keys.md` | Hand-maintained | Single-file Redis catalog |
| `docs/redis-key-registry-{tenant,global,events}.md` | Hand-maintained | Sharded deep variant |
| `docs/db-impact-map.md` | Hand-maintained | Single-file DB impact map |
| `docs/db-impact-map-{master,tenant,vector}.md` | Hand-maintained | Sharded deep variant |
| `docs/architecture.md` | Hand-maintained | Long-form architecture (lowercase) |
| `docs/ARCHITECTURE.md` | Hand-maintained | Design narrative (uppercase) — *why* |
| `docs/service-registry.md` | **GENERATED** by dotagent from `git.yaml` | Per-repo table |
| `docs/ops/service-registry.md` | Hand-maintained | Per-process pm2/port table |

The shape your project uses is your choice. Projects that follow this
sharded layered convention get richer navigation pointers; projects that
stick with the flat single-file defaults get the original layout — both
work without configuration changes.

The **only** path collision to be aware of:
- `docs/service-registry.md` (lowercase) is **GENERATED** by dotagent
  from `.agent/git.yaml` — list of git repos.
- `docs/ops/service-registry.md` is **HAND-MAINTAINED** — list of
  processes. Different file, different concept, no overlap.

---

## Verbatim source spec

_The text below is the canonical request that introduced this convention.
Preserve verbatim if you edit this document — it's the source of truth
for what dotagent does and doesn't do here._

> SUBJECT: Register a hand-maintained documentation structure as
> referenceable sources — DO NOT generate or own these files.
>
> CONTEXT: My project has a documentation system that I (the human) +
> Claude maintain by hand. I need dotagent to UNDERSTAND this structure
> and be able to REFERENCE it in the adapters/files dotagent renders
> (CLAUDE.md, AGENTS.md, source pointers, etc.) — so an agent reading
> the adapter knows these docs exist, what each holds, and how to
> navigate them.
>
> HARD BOUNDARY — dotagent's role here is READ + REFERENCE only:
>   - DO NOT generate, author, render-the-content-of, or overwrite any
>     of these files.
>   - DO NOT treat them as generated surfaces (they are NOT like
>     SCOPE.md / CONTRACTS.md).
>   - DO index them as SOURCES and surface pointers to them in the
>     rendered adapters, exactly as you already do for db-impact-map /
>     redis-key-registry / anti-patterns.
>   - The content is owned by humans + Claude. You only point at it.
>
> ENTRY POINT: feature_master.md is the index. An agent working on a
> feature should be pointed to feature_master.md → the matching
> FM-###-<slug>.md → then follow its file-path / service-name
> references into the deep registries.

---

## Related docs

- `CLAUDE_MD_DESIGN.md` — overall CLAUDE.md design.
- `SERVICE_REPO_CLAUDE_MD.md` — service-repo as child of project-root.
- `DERIVED_FILES_DESIGN.md` — what dotagent DOES generate (for contrast).
- `src/dotagent/canonical_structure.py` — schema entries.
- `src/dotagent/config.py` — default `sources.extra:` registration.
- `src/dotagent/render/manifest.py` — adapter rendering + the
  `_CATEGORY_PREFACE` callout.
- `tests/render/test_hand_maintained_docs.py` — regression tests.
