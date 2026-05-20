# Service-repo CLAUDE.md

Service-repo tier of dotagent's CLAUDE.md — a **child manifest** that surfaces both this service's local context AND the parent project-root's context via `../`-prefixed pointers.

For the overall four-layer design, see `CLAUDE_MD_DESIGN.md`. Implementation: `_SERVICE_REPO_ENTRIES` in `canonical_structure.py`.

---

## Three tiers, side by side

| Aspect | project-root | service-repo | single-repo |
|---|---|---|---|
| Detected by | `.agent/git.yaml` present | `parent:` in `config.yaml` | Neither |
| Renders `../` pointers | Never | Always | Never |
| Bug registry scope | Cross-service (`AGT-####`) | Service-local (`BE-####`, …) | Project bugs |
| Modules scope | Cross-service master modules | Service slices (may have `cross_module:`) | All modules |

---

## What the schema declares

The service-repo schema has three groups of entries:

### Group A — Local pointers
This service's own files: `.agent/{architecture,rules,style,patterns,preferences}.md`, `.agent/project/{plan.yaml,CONTRACTS.md}`, `docs/*.md`. Same shape as single-repo.

### Group B — Contract layer
Templated path patterns so the AI knows what to read at each cycle phase:

```
.agent/project/modules
.agent/project/modules/<id>/module.yaml
.agent/project/modules/<id>/PLAN.md                            (generated)
.agent/project/modules/<id>/cycles/<NN>/contract.md            (live)
.agent/project/modules/<id>/cycles/<NN>/contract.frozen.md     (generated; immutable)
.agent/project/modules/<id>/cycles/<NN>/dev-handoff.md
.agent/project/modules/<id>/cycles/<NN>/qa-findings.md
.agent/project/modules/<id>/completion.md
.agent/project/modules/<id>/HISTORY.md                          (generated)
```

If `module.yaml` declares `cross_module: <project-root-module>`, this is a SLICE of a cross-service module — coordinate via the parent's cycle contract.

### Group C — Inherited pointers (`../`-prefixed)
Project-root context surfaced into the service-repo manifest. Each carries `INHERITED ·` in its description so precedence is visible at-a-glance:

```
../.agent/{project_brief,rules,git.md,architecture,style,patterns}.md
../.agent/project/{plan.yaml,SCOPE.md,CONTRACTS.md,modules,dashboard.md}
../contracts.md
../docs/{service-registry,shared-contracts,dependency-map,architecture,bug-registry,anti-patterns}.md
```

The renderer groups inherited entries **alongside their local equivalents** in the same category section (local first, then inherited).

---

## Design defaults (locked)

1. **Hybrid contract re-statement** — service-repo points at both `.agent/project/CONTRACTS.md` (local) AND `../contracts.md` (cross-repo rollup). No content duplication; AI reads both.
2. **Cross-module slices prominent** — `.agent/project/modules` entry calls out that `cross_module:` slices coordinate via the parent's cycle.
3. **Service-first bug registry** — service-local `docs/bug-registry.md` with cross-ref pointer to `../docs/bug-registry.md` for `AGT-####` ids. Cross-refs go from local → cross, never the reverse.
4. **Service-registry pointer only** — don't enumerate sibling services; point at `../docs/service-registry.md` and let the AI navigate.

---

## Why `git.yaml` is project-root only

`.agent/git.yaml` is the source of truth for branch rules + cross-repo topology — a project-root concern. Service-repo devs never edit YAML; they read the rendered dashboard `git.md`. So the service-repo manifest surfaces `../.agent/git.md` (in MUST_READ) but **not** `../.agent/git.yaml`.

A regression test (`test_git_yaml_is_project_root_only_not_service_repo`) asserts the YAML stays out of the schema AND the rendered manifest.

---

## Auto-regeneration on docs change

The pre-commit hook (`dotagent observe pre-commit`) re-renders every enabled adapter when staged files include `docs/*.md`. Opt-out via `.agent/config.yaml`:

```yaml
hooks:
  auto_regen_on_docs: false   # default: true
```

Failures land in `.agent/log/` and never block the commit.

---

## CI guarantees

In addition to the three universal coverage gates (see `CLAUDE_MD_DESIGN.md`), `tests/render/test_service_repo_child.py` asserts:

- Every local contract-layer path is in the schema and renders.
- Every `../`-prefixed inherited path is in the schema and renders.
- MUST_READ section includes inherited `project_brief`, `rules`, `git.md`.
- Inherited entries carry the `INHERITED` marker in render.
- `../.agent/git.yaml` is NOT in the schema (regression guard).

---

## Known limitations

1. Renderer doesn't load parent files at render time — only declares pointers. AI reads on demand.
2. Doesn't validate that parent files exist on disk — `dotagent doctor` handles that separately.
3. All service-repo manifests render the same `../`-prefixed pointers regardless of `parent:` value. Relative-path math is the AI's job.

---

## Related

- `CLAUDE_MD_DESIGN.md` — four-layer design + ownership rule
- `DERIVED_FILES_DESIGN.md` — what regenerates on each `dotagent sync`
- `src/dotagent/canonical_structure.py` — `_SERVICE_REPO_ENTRIES`
- `tests/render/test_service_repo_child.py` — service-repo-specific coverage gates
